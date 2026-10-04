import asyncio
import json
import pytest
from httpx import AsyncClient
from api.job_manager import JobManager

@pytest.mark.asyncio
async def test_sse_race_window_historical_and_live():
    """
    Verify that an SSE client does not miss events published precisely while
    it is connecting and fetching historical events.
    """
    task_id = "test-sse-task-123"
    
    # We don't need a full database for this if we test the logic.
    # Actually, JobManager.add_worker_event interacts with the DB. Let's set it up.
    import sqlite3
    from api.job_manager import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    # Insert dummy job
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status) VALUES (?, ?, ?)",
        (task_id, "foo", "QUEUED")
    )
    conn.commit()
    conn.close()

    # Create one historical event
    now = "2023-01-01T00:00:00Z"
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = 'QUEUED' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    JobManager.record_informational_event(task_id, "STARTING", "started", {}, now, sequence=1)
    
    # Run the generator
    from api.sse import event_generator
    gen = event_generator(task_id, start_seq=-2)

    # First event should be historical
    evt1 = await anext(gen)
    assert json.loads(evt1["data"])["sequence"] == 1
    
    # While generator is waiting for next event, a live event is posted
    
    # Must manually update jobs table to satisfy valid transitions
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = 'STARTING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    JobManager.record_informational_event(task_id, "RUNNING", "running", {}, now, sequence=2)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = 'RUNNING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    JobManager.record_informational_event(task_id, "COMPLETED", "pipeline_complete", {}, now, sequence=3)
    
    # The generator should now yield the live events and terminate
    evt2 = await anext(gen)
    assert json.loads(evt2["data"])["sequence"] == 2
    
    evt3 = await anext(gen)
    assert json.loads(evt3["data"])["sequence"] == 3
    
    # Should be done
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

@pytest.mark.asyncio
async def test_event_authority():
    """Verify backend monotonically allocates sequences when sequence=None is passed."""
    task_id = "test-auth-task-456"
    import sqlite3
    from api.job_manager import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status) VALUES (?, ?, ?)",
        (task_id, "foo", "QUEUED")
    )
    conn.commit()
    conn.close()

    now = "2023-01-01T00:00:00Z"
    # Worker sends None for sequence (enforced by the webhook)
    _, seq1 = JobManager.record_informational_event(task_id, "STARTING", "started", {}, now, sequence=None)
    _, seq2 = JobManager.record_informational_event(task_id, "RUNNING", "running", {}, now, sequence=None)
    
    assert seq1 == 1
    assert seq2 == 2
    
    # Event idempotency still works if duplicate sequence explicitly injected by backend (unlikely)
    success, seq3 = JobManager.record_informational_event(task_id, "COMPLETED", "pipeline_complete", {}, now, sequence=2)
    assert success is False
    assert seq3 == 2
