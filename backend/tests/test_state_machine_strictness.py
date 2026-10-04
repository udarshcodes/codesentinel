import pytest
import sqlite3
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager, DB_PATH

def test_save_worker_state_prevents_invalid_transitions():
    task_id = "test_strictness_worker_123"
    worker_id = "worker_123"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status) VALUES (?, ?, ?)",
        (task_id, worker_id, "WAITING_FOR_APPROVAL")
    )
    conn.commit()
    conn.close()

    # Attempt to transition WAITING_FOR_APPROVAL -> RUNNING via save_worker_state (should throw ValueError)
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state(task_id, worker_id, "RUNNING", {})

    # Attempt to transition WAITING_FOR_APPROVAL -> COMPLETED via save_worker_state
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state(task_id, worker_id, "COMPLETED", {})

    # Change to RUNNING natively, then simulate valid worker transitions
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'RUNNING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()

    # RUNNING -> RUNNING (Heartbeat) is valid
    assert JobManager.save_worker_state(task_id, worker_id, "RUNNING", {}) is True

    # RUNNING -> WAITING_FOR_LLM_CAPACITY is valid with correct payload
    valid_llm_state = {
        "llm_waiting_state": True,
        "next_retry": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "last_llm_model": "gpt-4", "last_llm_error": "rate limited"
    }
    assert JobManager.save_worker_state(task_id, worker_id, "WAITING_FOR_LLM_CAPACITY", valid_llm_state) is True

def test_negative_bypass_validation():
    """Verify that removing bypass_validation effectively prevents forced invalid transitions."""
    task_id = "test_strictness_bypass"
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
        cursor.execute("INSERT INTO jobs (task_id, status) VALUES (?, ?)", (task_id, "NEEDS_REVIEW"))
        conn.commit()
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Needs review -> RUNNING
        with pytest.raises(ValueError, match="Invalid state transition: NEEDS_REVIEW -> RUNNING"):
            JobManager.transition_job_state(cursor, task_id, "RUNNING", timestamp=now)
            
        # COMPLETED -> DISPATCHING
        cursor.execute("UPDATE jobs SET status = 'COMPLETED' WHERE task_id = ?", (task_id,))
        conn.commit()
        with pytest.raises(ValueError, match="Invalid state transition: COMPLETED -> DISPATCHING"):
            JobManager.transition_job_state(cursor, task_id, "DISPATCHING", timestamp=now)
            
        # FAILED -> RUNNING
        cursor.execute("UPDATE jobs SET status = 'FAILED' WHERE task_id = ?", (task_id,))
        conn.commit()
        with pytest.raises(ValueError, match="Invalid state transition: FAILED -> RUNNING"):
            JobManager.transition_job_state(cursor, task_id, "RUNNING", timestamp=now)

        # WAITING_FOR_APPROVAL -> DISPATCHING
        cursor.execute("UPDATE jobs SET status = 'WAITING_FOR_APPROVAL' WHERE task_id = ?", (task_id,))
        conn.commit()
        with pytest.raises(ValueError, match="Invalid state transition: WAITING_FOR_APPROVAL -> DISPATCHING"):
            JobManager.transition_job_state(cursor, task_id, "DISPATCHING", timestamp=now)
            
        # RUNNING -> DISPATCHING
        cursor.execute("UPDATE jobs SET status = 'RUNNING' WHERE task_id = ?", (task_id,))
        conn.commit()
        with pytest.raises(ValueError, match="Invalid state transition: RUNNING -> DISPATCHING"):
            JobManager.transition_job_state(cursor, task_id, "DISPATCHING", timestamp=now)
            
    finally:
        conn.close()
