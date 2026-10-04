import pytest
import sqlite3
from datetime import datetime, timezone, timedelta
import os
from api.job_manager import JobManager, DB_PATH

def setup_job(task_id: str, status: str, next_retry=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM job_events WHERE task_id = ?", (task_id,))
    cursor.execute("INSERT INTO jobs (task_id, status, next_retry) VALUES (?, ?, ?)", (task_id, status, next_retry))
    conn.commit()
    conn.close()

def test_atomic_dispatch_event():
    task_id = "test_atomic_dispatch"
    setup_job(task_id, "WAITING_FOR_DISPATCH")
    
    worker_id = JobManager.claim_waiting_job(task_id)
    assert worker_id is not None
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, worker_attempt_id, dispatch_count FROM jobs WHERE task_id = ?", (task_id,))
    job = cursor.fetchone()
    
    assert job[0] == "DISPATCHING"
    assert job[1] == worker_id
    assert job[2] == 1
    
    cursor.execute("SELECT event_name, status, sequence FROM job_events WHERE task_id = ?", (task_id,))
    events = cursor.fetchall()
    
    # Verify exactly one dispatch event
    assert len(events) == 1
    assert events[0][0] == "dispatch"
    assert events[0][1] == "DISPATCHING"
    assert events[0][2] == 1
    conn.close()

def test_dispatch_failure_handling():
    task_id = "test_dispatch_failure"
    setup_job(task_id, "WAITING_FOR_DISPATCH")
    worker_id = JobManager.claim_waiting_job(task_id)
    
    # Simulate dispatch failure
    JobManager.record_dispatch_failure(task_id, "Mock GitHub API Error", worker_id)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, worker_attempt_id, next_retry FROM jobs WHERE task_id = ?", (task_id,))
    job = cursor.fetchone()
    
    assert job[0] == "WAITING_FOR_DISPATCH"
    assert job[1] is None  # cleared
    assert job[2] is not None # next_retry set
    
    cursor.execute("SELECT event_name, status FROM job_events WHERE task_id = ? ORDER BY sequence DESC LIMIT 1", (task_id,))
    evt = cursor.fetchone()
    assert evt[0] == "dispatch_failed"
    assert evt[1] == "WAITING_FOR_DISPATCH"
    conn.close()

from unittest.mock import patch

def test_claim_waiting_job_broadcast_success():
    task_id = "test_dispatch_broadcast"
    setup_job(task_id, "WAITING_FOR_DISPATCH")
    
    with patch("api.job_manager.JobManager._broadcast_event") as mock_broadcast:
        worker_id = JobManager.claim_waiting_job(task_id)
        
        assert worker_id is not None
        mock_broadcast.assert_called_once()
        
        args, kwargs = mock_broadcast.call_args
        assert args[0] == task_id
        assert args[1] == "dispatch"
        assert args[2]["worker_attempt_id"] == worker_id
        assert args[2]["dispatch_count"] == 1
        assert args[2]["source"] == "claim"
        assert args[3] == "DISPATCHING"

def test_claim_waiting_job_broadcast_failure_resilience():
    task_id = "test_dispatch_resilience"
    setup_job(task_id, "WAITING_FOR_DISPATCH")
    
    with patch("api.job_manager.JobManager._broadcast_event", side_effect=Exception("Queue full")):
        worker_id = JobManager.claim_waiting_job(task_id)
        
        # Must still succeed and return worker_id
        assert worker_id is not None
        
        # Verify db was committed
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,))
        status = cursor.fetchone()[0]
        assert status == "DISPATCHING"
        conn.close()

def test_stale_recovery_atomic():
    task_id = "test_stale_recovery"
    # Create an old running job
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM job_events WHERE task_id = ?", (task_id,))
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, worker_heartbeat_at) VALUES (?, ?, ?, ?)", 
        (task_id, "RUNNING", "old_worker", old_time)
    )
    conn.commit()
    conn.close()
    
    new_worker_id = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker_id is not None
    assert new_worker_id != "old_worker"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, worker_attempt_id FROM jobs WHERE task_id = ?", (task_id,))
    job = cursor.fetchone()
    assert job[0] == "DISPATCHING"
    assert job[1] == new_worker_id
    
    cursor.execute("SELECT event_name, status FROM job_events WHERE task_id = ?", (task_id,))
    events = cursor.fetchall()
    
    # Only one event ("worker_revoked")
    assert len(events) == 1
    assert events[0][0] == "worker_revoked"
    assert events[0][1] == "DISPATCHING"
    conn.close()

def test_llm_cooldown_bypass_prevention():
    task_id = "test_cooldown_bypass"
    future_time = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    setup_job(task_id, "WAITING_FOR_LLM_CAPACITY", future_time)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="Invalid state transition: WAITING_FOR_LLM_CAPACITY -> WAITING_FOR_DISPATCH"):
        JobManager.transition_job_state(cursor, task_id, "WAITING_FOR_DISPATCH", timestamp=now)
    conn.close()

def test_terminal_state_protection():
    now = datetime.now(timezone.utc).isoformat()
    for terminal_state in ["COMPLETED", "FAILED", "NEEDS_REVIEW"]:
        task_id = f"test_terminal_{terminal_state}"
        setup_job(task_id, terminal_state)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        with pytest.raises(ValueError, match=f"Invalid state transition: {terminal_state} -> DISPATCHING"):
            JobManager.transition_job_state(cursor, task_id, "DISPATCHING", timestamp=now)
        conn.close()
