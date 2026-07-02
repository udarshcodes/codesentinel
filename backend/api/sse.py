import json
from fastapi import APIRouter
import asyncio
from sse_starlette.sse import EventSourceResponse
from api.job_manager import JobManager

router = APIRouter()

async def event_generator(task_id: str):
    # 1. Fetch historical events from JobManager
    historical_events = JobManager.get_events(task_id, after_sequence=-1)
    last_sequence = -1
    
    is_completed = False
    
    # Yield historical events first
    for evt in historical_events:
        yield {
            "event": evt["event"],
            "data": json.dumps(evt["data"]),
        }
        last_sequence = evt["sequence"]
        if evt["event"] in ["pipeline_complete", "error"]:
            is_completed = True
            
    if is_completed:
        return
        
    # 2. Subscribe to live events
    q = JobManager.subscribe(task_id)
    try:
        while True:
            payload = await q.get()
            
            # Skip if we already yielded this sequence historically
            if payload["sequence"] <= last_sequence:
                continue
                
            yield {
                "event": payload["event"],
                "data": json.dumps(payload["data"]),
            }
            if payload["event"] in ["pipeline_complete", "error"]:
                break
    except asyncio.CancelledError:
        print(f"SSE client disconnected for task {task_id}")
    except Exception as e:
        print(f"SSE stream error: {e}")
    finally:
        JobManager.unsubscribe(task_id, q)

@router.get("/v1/stream")
@router.get("/stream")
async def stream_pipeline(task_id: str = None):
    if not task_id:
        return {"error": "Missing task_id"}

    return EventSourceResponse(event_generator(task_id))
