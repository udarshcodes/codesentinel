import json
from fastapi import APIRouter, Request
import asyncio
from sse_starlette.sse import EventSourceResponse
from orchestrator import app as langgraph_app, sse_queues

router = APIRouter()

def make_serializable(obj):
    """Recursively convert non-serializable objects to strings."""
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)

async def run_pipeline_worker(task_id: str, repo_url: str):
    state = {
        "task_id": task_id,
        "repo_url": repo_url,
        "repo_local_path": "",
        "knowledge_graph": {},
        "dependency_findings": [],
        "static_findings": [],
        "investigated_issues": [],
        "repair_plan": [],
        "patches": [],
        "validation_results": [],
        "security_verified": False,
        "pr_url": "",
        "pr_error": "",
        "retry_count": 0,
        "awaiting_approval": False,
        "confidence_score": 0.0,
        "token_usage": {},
    }
    
    # We create the queue here if it doesn't exist, so that manual SSE events like approval
    # can be injected via the orchestrator.
    if task_id not in sse_queues:
        sse_queues[task_id] = asyncio.Queue()
        
    async def emit(event: str, data: dict):
        if task_id in sse_queues:
            try:
                await sse_queues[task_id].put({"event": event, "data": data})
            except Exception:
                pass

    await emit("pipeline_started", {"repo_url": repo_url})
    
    final_pr_url = ""
    final_pr_error = ""
    final_confidence = 0.0
    
    try:
        # We need to run astream and concurrently poll the queue for manual events
        # like we did in the old code to support the approval_resolved event
        astream_iter = langgraph_app.astream(state)
        astream_task = asyncio.create_task(anext(astream_iter, None))
        
        q = sse_queues[task_id]
        queue_task = asyncio.create_task(q.get())
        
        while True:
            done, pending = await asyncio.wait(
                {astream_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # This allows the background worker to "drain" manual messages sent by the orchestrator 
            # (e.g. approval messages from routes.py) and broadcast them down the line
            if queue_task in done:
                payload = queue_task.result()
                # Just re-emit the message so the frontend gets it
                # Wait, if we emit it, we put it back in the queue! We'll cause an infinite loop!
                # Actually, the old code yielded it directly to SSE. 
                # Since SSE is just reading from the queue now, we don't need to do anything here for manual events!
                # Wait, if `routes.py` puts "approval_resolved" in the queue, the SSE reader will read it!
                # We don't need to poll the queue in the worker anymore, EXCEPT to unblock the pipeline!
                # Oh! The pipeline unblocks via `event.set()` in `approval_events[task_id]['event']` from `routes.py`!
                pass # We don't need to poll the queue!
                
            if astream_task in done:
                output = astream_task.result()
                if output is None: # End of stream
                    break
                    
                for node_name, state_update in output.items():
                    safe_update = make_serializable(state_update)
                    
                    if "pr_url" in safe_update:
                        final_pr_url = safe_update["pr_url"]
                    if "pr_error" in safe_update:
                        final_pr_error = safe_update["pr_error"]
                    if "confidence_score" in safe_update:
                        final_confidence = safe_update["confidence_score"]
                        
                    event_data = {
                        "agent": node_name,
                        "status": "success",
                        "data": safe_update
                    }
                    await emit("agent_complete", event_data)
                    
                astream_task = asyncio.create_task(anext(astream_iter, None))
                
        await emit("pipeline_complete", {
            "status": "done",
            "pr_url": final_pr_url,
            "pr_error": final_pr_error,
            "confidence_score": final_confidence
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await emit("error", {"error": str(e)})

async def event_generator(task_id: str):
    if task_id not in sse_queues:
        sse_queues[task_id] = asyncio.Queue()
        
    q = sse_queues[task_id]
    
    try:
        while True:
            payload = await q.get()
            yield {
                "event": payload.get("event", "message"),
                "data": json.dumps(payload.get("data", payload))
            }
            if payload.get("event") in ["pipeline_complete", "error"]:
                break
    except asyncio.CancelledError:
        print(f"SSE client disconnected for task {task_id}")
    except Exception as e:
        print(f"SSE stream error: {e}")

@router.get("/stream")
async def stream_pipeline(request: Request, repo_url: str = None, task_id: str = None):
    # Support backward compatibility
    if not task_id and repo_url:
        task_id = repo_url.split('/')[-1]
    
    if not task_id:
        return {"error": "Missing task_id"}
        
    return EventSourceResponse(event_generator(task_id))