import asyncio

approval_events: dict[str, dict] = {}
sse_queues: dict[str, asyncio.Queue] = {}

async def broadcast_sse(task_id: str, payload: dict):
    if task_id in sse_queues:
        await sse_queues[task_id].put(payload)
