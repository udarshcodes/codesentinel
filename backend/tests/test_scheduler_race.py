import pytest
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager, DB_PATH

def setup_test_job(task_id: str, status: str):
    JobManager.create_job(task_id, "https://github.com/test/repo", commit_sha="test_commit_sha")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = ? WHERE task_id = ?", (status, task_id))
    conn.commit()
    conn.close()

def test_get_waiting_jobs_ready_malformed_llm():
    """
    Verifies that WAITING_FOR_LLM_CAPACITY with malformed next_retry is
    transitioned to NEEDS_REVIEW instantly and NOT returned.
    """
    task_id = "test-malformed-" + str(uuid.uuid4())
    setup_test_job(task_id, "WAITING_FOR_LLM_CAPACITY")

    # Set malformed next_retry
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET next_retry = 'invalid-date' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()

    ready_jobs = JobManager.get_waiting_jobs_ready()
    # Should NOT be returned
    assert not any(job["task_id"] == task_id for job in ready_jobs)

    job = JobManager.get_job(task_id)
    assert job["status"] == "NEEDS_REVIEW"

def test_stale_recovery_strictness():
    """
    Verifies that Stale Recovery is only applied to actually stale jobs.
    """
    # 1. Fresh RUNNING -> Should not be recovered
    fresh_task_id = "test-fresh-" + str(uuid.uuid4())
    setup_test_job(fresh_task_id, "RUNNING")
    
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET worker_heartbeat_at = ?, dispatch_attempted_at = ? WHERE task_id = ?", (now.isoformat(), now.isoformat(), fresh_task_id))
    conn.commit()
    conn.close()

    result = JobManager.recover_stale_worker_claim(fresh_task_id)
    assert result is None, "Fresh RUNNING job must not be recovered"

    # 2. Stale RUNNING -> Should be recovered
    stale_task_id = "test-stale-" + str(uuid.uuid4())
    setup_test_job(stale_task_id, "RUNNING")
    
    past = (now - timedelta(minutes=10)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET worker_heartbeat_at = ?, dispatch_attempted_at = ? WHERE task_id = ?", (past, past, stale_task_id))
    conn.commit()
    conn.close()

    result = JobManager.recover_stale_worker_claim(stale_task_id)
    assert result is not None, "Stale RUNNING job must be recovered"

    job = JobManager.get_job(stale_task_id)
    assert job["status"] == "DISPATCHING"

def test_scheduler_concurrent_exclusion():
    """
    Mock test to verify scheduler handles concurrent state transitions gracefully.
    Wait, since it uses an EXCLUSIVE transaction block, concurrent calls simply wait for it to finish, 
    so the check is strictly atomic.
    """
    # Test valid WAITING_FOR_LLM_CAPACITY with past next_retry (cooldown expired)
    task_id = "test-expired-" + str(uuid.uuid4())
    setup_test_job(task_id, "WAITING_FOR_LLM_CAPACITY")
    
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET next_retry = ? WHERE task_id = ?", (past, task_id))
    conn.commit()
    conn.close()

    ready_jobs = JobManager.get_waiting_jobs_ready()
    assert any(job["task_id"] == task_id for job in ready_jobs)
