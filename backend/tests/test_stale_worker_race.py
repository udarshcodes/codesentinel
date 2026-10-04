import pytest
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager, DB_PATH

@pytest.fixture
def clean_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()

def test_stale_worker_race_handling(clean_db):
    task_id = "test_stale_race"
    w1 = "worker1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Insert worker 1 with an old heartbeat
    old_hb = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, w1, "RUNNING", old_hb)
    )
    conn.commit()
    conn.close()
    
    # 1. Claim job (simulating orchestrator recovering a stale job)
    w2 = JobManager.recover_stale_worker_claim(task_id)
    assert w2 is not None
    assert w2 != w1
    
    # 2. Worker 1 tries to submit state
    # This should fail because w1 is no longer the active worker_attempt_id
    with pytest.raises(ValueError, match="Stale worker attempt"):
        JobManager.save_worker_state(task_id, w1, "RUNNING", {})
    
    # 3. Worker 1 tries to submit heartbeat
    # JobManager does not have a record_heartbeat method, it is done via routes.
    # We will test an event instead.
    
    # 4. Worker 1 tries to post an event
    with pytest.raises(ValueError, match="Stale worker attempt"):
        JobManager.add_worker_event(task_id, w1, "RUNNING", "test_event", {}, datetime.now(timezone.utc).timestamp())
    
    # 5. Worker 1 tries to record LLM exhaustion
    res = JobManager.set_worker_waiting_capacity(task_id, w1, "2099-01-01T00:00:00Z", {"last_llm_model": "gpt-4", "last_llm_error": "rate limited"})
    assert res is False
    
    # 6. Verify that the job was transitioning correctly when claimed (DISPATCHING)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, worker_attempt_id FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    assert row[0] == "DISPATCHING"
    assert row[1] == w2
    
    # Check that worker_revoked event was inserted
    cursor.execute("SELECT event_name FROM job_events WHERE task_id = ? AND event_name = 'worker_revoked'", (task_id,))
    events = cursor.fetchall()
    assert len(events) == 1
    conn.close()

def test_stale_worker_race_commit_failure(clean_db, monkeypatch):
    """
    Simulates a commit failure during recover_stale_worker_claim to ensure
    no SSE broadcast occurs.
    """
    task_id = "test_stale_commit_fail"
    w1 = "worker1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    old_hb = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, w1, "RUNNING", old_hb)
    )
    conn.commit()
    conn.close()

    broadcast_called = False
    def mock_broadcast(*args, **kwargs):
        nonlocal broadcast_called
        broadcast_called = True

    monkeypatch.setattr("api.job_manager.JobManager._broadcast_event", mock_broadcast)

    original_connect = sqlite3.connect
    def mock_connect(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        # Create a wrapper class to intercept commit
        class ConnWrapper:
            def __getattr__(self, name):
                return getattr(conn, name)
            def commit(self):
                raise sqlite3.OperationalError("Simulated commit failure")
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        return ConnWrapper()

    monkeypatch.setattr("api.job_manager.sqlite3.connect", mock_connect)

    try:
        JobManager.recover_stale_worker_claim(task_id)
    except Exception:
        pass
        
    assert not broadcast_called, "Broadcast should not happen if commit fails"
