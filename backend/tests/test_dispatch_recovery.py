import pytest
import sqlite3
import json
import uuid
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager, DB_PATH, init_db

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield

def test_record_dispatch_failure_cannot_resurrect_terminal_states():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for status in ["COMPLETED", "FAILED", "NEEDS_REVIEW", "RUNNING", "WAITING_FOR_APPROVAL", "WAITING_FOR_LLM_CAPACITY"]:
        task_id = "test-term-resurrect-" + str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO jobs (task_id, repo_url, status, worker_attempt_id) VALUES (?, 'repo', ?, 'worker1')",
            (task_id, status)
        )
        conn.commit()
        
        try:
            JobManager.record_dispatch_failure(task_id, "Some error", "worker1")
        except ValueError:
            pass
        
        row = cursor.execute("SELECT status, worker_attempt_id FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
        assert row is not None
        # Verify status did not change
        assert row[0] == status
        # Verify attempt ID did not clear
        assert row[1] == "worker1"

    conn.close()

def test_record_dispatch_failure_stale_worker_safe():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-stale-worker-" + str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, worker_attempt_id) VALUES (?, 'repo', 'DISPATCHING', 'worker_B')",
        (task_id,)
    )
    conn.commit()
    
    # worker_A tries to record a dispatch failure but it's stale
    JobManager.record_dispatch_failure(task_id, "Some error", "worker_A")
    
    row = cursor.execute("SELECT status, worker_attempt_id FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row[0] == "DISPATCHING"
    assert row[1] == "worker_B"
    conn.close()

def test_approval_rejection_dispatch_failure_regression():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-reject-resurrect-" + str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, worker_attempt_id) VALUES (?, 'repo', 'NEEDS_REVIEW', 'worker_old')",
        (task_id,)
    )
    conn.commit()
    
    # Simulate an old dispatch failure reporting late after the job was already rejected
    JobManager.record_dispatch_failure(task_id, "Some error", "worker_old")
    
    row = cursor.execute("SELECT status, worker_attempt_id FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row[0] == "NEEDS_REVIEW"
    assert row[1] == "worker_old"
    conn.close()
