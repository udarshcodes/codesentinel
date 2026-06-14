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

async def event_generator(repo_url: str):
    # Initial state — provide sane defaults for all PipelineState fields
    state = {
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
    
    task_id = repo_url.split('/')[-1] # Simplistic task_id for phase 1 mock
    state["task_id"] = task_id
    
    # Initialize the queue for this task
    q = asyncio.Queue()
    sse_queues[task_id] = q
    
    yield {
        "event": "pipeline_started",
        "data": json.dumps({"repo_url": repo_url})
    }

    try:
        # Create an async generator for the LangGraph pipeline
        astream_iter = langgraph_app.astream(state)
        
        astream_task = asyncio.create_task(anext(astream_iter, None))
        queue_task = asyncio.create_task(q.get())
        
        final_pr_url = ""
        final_pr_error = ""
        final_confidence = 0.0
        
        while True:
            done, pending = await asyncio.wait(
                {astream_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Handle manual SSE events broadcasted from the queue (e.g. approval_required)
            if queue_task in done:
                payload = queue_task.result()
                yield {
                    "event": payload.get("event", "message"),
                    "data": json.dumps(payload.get("data", payload))
                }
                queue_task = asyncio.create_task(q.get())
                
            # Handle LangGraph state yields
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
                    
                    yield {
                        "event": "agent_complete",
                        "data": json.dumps(event_data)
                    }
                    
                astream_task = asyncio.create_task(anext(astream_iter, None))
                
        yield {
            "event": "pipeline_complete",
            "data": json.dumps({
                "status": "done",
                "pr_url": final_pr_url,
                "pr_error": final_pr_error,
                "confidence_score": final_confidence
            })
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {
            "event": "error",
            "data": json.dumps({"error": str(e)})
        }
    finally:
        # Cleanup
        sse_queues.pop(task_id, None)

@router.get("/stream")
async def stream_pipeline(repo_url: str, request: Request):
    return EventSourceResponse(event_generator(repo_url))