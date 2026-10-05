import json
from fastapi import APIRouter
import asyncio
from sse_starlette.sse import EventSourceResponse
from api.job_manager import JobManager

router = APIRouter()


async def event_generator(task_id: str, start_seq: int = None):
    # Subscribe FIRST to prevent missing events between DB fetch and subscription
    q = JobManager.subscribe(task_id)
    
    # If no cursor provided, fetch all events (sequence > -1)
    db_seq = start_seq if start_seq is not None else -1
    historical_events = JobManager.get_events(task_id, since_sequence=db_seq)
    last_sequence = db_seq
    is_completed = False

    for evt in historical_events:
        evt_data = evt["data"].copy() if isinstance(evt["data"], dict) else {}
        evt_data["sequence"] = evt["sequence"]
        evt_data["timestamp"] = evt["timestamp"]
        evt_data["status"] = evt["status"]
        
        yield {
            "id": str(evt["sequence"]),
            "event": evt["event"],
            "data": json.dumps(evt_data),
        }
        last_sequence = evt["sequence"]
        if evt["status"] in ["COMPLETED", "FAILED", "NEEDS_REVIEW"]:
            is_completed = True

    if is_completed:
        JobManager.unsubscribe(task_id, q)
        return

    try:
        while True:
            payload = await q.get()

            # Deduplicate sequences already yielded historically
            if payload["sequence"] <= last_sequence:
                continue

            payload_data = payload["data"].copy() if isinstance(payload["data"], dict) else {}
            payload_data["sequence"] = payload["sequence"]
            payload_data["timestamp"] = payload["timestamp"]
            payload_data["status"] = payload["status"]

            yield {
                "id": str(payload["sequence"]),
                "event": payload["event"],
                "data": json.dumps(payload_data),
            }
            if payload["status"] in ["COMPLETED", "FAILED", "NEEDS_REVIEW"]:
                break
    except asyncio.CancelledError:
        print(f"SSE client disconnected for task {task_id}")
    except Exception as e:
        print(f"SSE stream error: {e}")
    finally:
        JobManager.unsubscribe(task_id, q)


from fastapi import APIRouter, Header

@router.get("/v1/stream")
@router.get("/stream")
async def stream_pipeline(
    task_id: str = None, 
    capability: str = None,
    last_event_id: str = None,
    last_event_id_header: str = Header(None, alias="Last-Event-ID")
):
    if not task_id:
        return {"error": "Missing task_id"}
        
    if not capability or not JobManager.validate_sse_capability(capability, task_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid or expired SSE capability")

    # Replay Protocol: Last-Event-ID header takes precedence, fallback to query param
    resolved_last_id = last_event_id_header or last_event_id
    
    start_seq = None
    if resolved_last_id and resolved_last_id.lstrip('-').isdigit():
        start_seq = int(resolved_last_id)

    return EventSourceResponse(event_generator(task_id, start_seq), ping=15)
