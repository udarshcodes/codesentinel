import asyncio

approval_events: dict[str, dict] = {}
sse_queues: dict[str, asyncio.Queue] = {}

class Metrics:
    queue_depth = 0
    scan_duration_ms = 0
    failed_jobs = 0
    completed_jobs = 0

metrics = Metrics()

async def broadcast_sse(task_id: str, payload: dict):
    if task_id in sse_queues:
        await sse_queues[task_id].put(payload)
