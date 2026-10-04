import pytest
import asyncio
import sqlite3
import json
from datetime import datetime, timezone
import os

from api.job_manager import JobManager, DB_PATH

@pytest.mark.asyncio
async def test_sse_deduplication():
    task_id = "test_sse_replay_123"
    
    # Ensure clean state
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM job_events WHERE task_id = ?", (task_id,))
    
    cursor.execute("INSERT INTO jobs (task_id, status) VALUES (?, ?)", (task_id, "QUEUED"))
    
    # 1. Event A exists in DB
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO job_events (task_id, sequence, status, event_name, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, 1, "STARTING", "pipeline_start", '{"msg": "A"}', now)
    )
    cursor.execute("UPDATE jobs SET status = 'STARTING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()

    # 2. Client connects with last_sequence = -1
    from api.sse import event_generator
    stream_iter = event_generator(task_id, -1)
    
    event_a = await asyncio.wait_for(anext(stream_iter), timeout=1.0)
    assert event_a["id"] == "1"
    assert event_a["event"] == "pipeline_start"
    data_a = json.loads(event_a["data"])
    assert data_a["msg"] == "A"
    
    # 3. B is inserted using the standard JobManager event poster
    # This simulates B arriving to the queue
    JobManager.record_informational_event(task_id, "RUNNING", "pipeline_update", {"msg": "B"}, now)
    
    event_b = await asyncio.wait_for(anext(stream_iter), timeout=1.0)
    assert event_b["id"] == "2"
    assert event_b["event"] == "pipeline_update"
    data_b = json.loads(event_b["data"])
    assert data_b["msg"] == "B"
    
    # 4. C arrives
    JobManager.record_informational_event(task_id, "COMPLETED", "pipeline_complete", {"msg": "C"}, now)
    
    event_c = await asyncio.wait_for(anext(stream_iter), timeout=1.0)
    assert event_c["id"] == "3"
    assert event_c["event"] == "pipeline_complete"
    data_c = json.loads(event_c["data"])
    assert data_c["msg"] == "C"

    # 5. Client disconnects and reconnects with sequence 2 (Last-Event-ID)
    stream_iter_2 = event_generator(task_id, 2)
    event_c_replayed = await asyncio.wait_for(anext(stream_iter_2), timeout=1.0)
    assert event_c_replayed["id"] == "3"
    assert event_c_replayed["event"] == "pipeline_complete"
