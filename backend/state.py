import asyncio
import threading

approval_events: dict[str, dict] = {}
sse_queues: dict[str, asyncio.Queue] = {}

class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.queue_depth = 0
        self.scan_duration_ms = 0
        self.failed_jobs = 0
        self.completed_jobs = 0

    def increment(self, attr: str, value: int = 1):
        with self._lock:
            setattr(self, attr, getattr(self, attr) + value)

    def decrement(self, attr: str, value: int = 1):
        with self._lock:
            setattr(self, attr, max(0, getattr(self, attr) - value))

    def set_val(self, attr: str, value):
        with self._lock:
            setattr(self, attr, value)

metrics = Metrics()

async def broadcast_sse(task_id: str, payload: dict):
    if task_id in sse_queues:
        await sse_queues[task_id].put(payload)
