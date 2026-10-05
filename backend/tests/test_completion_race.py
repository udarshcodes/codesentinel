import pytest
from datetime import datetime, timezone
import json
from api.job_manager import JobManager
from api.db import get_connection

@pytest.fixture
def clean_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM jobs")
    conn.commit()
    return conn

def test_dispatching_to_completed_valid_transition(clean_db):
    task_id = "task-completed-race"
    cursor = clean_db.cursor()
    
    # 1. Create a job and move it to DISPATCHING (simulating a stale worker recovery)
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, repo_url, worker_attempt_id, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "DISPATCHING", "https://github.com/foo/bar", "attempt-1", now, now)
    )
    clean_db.commit()
    
    # 2. Worker resumes, sees no nodes left, immediately posts pipeline_complete
    success, seq = JobManager.add_worker_event(
        task_id=task_id,
        status="COMPLETED",
        event_name="pipeline_complete",
        data={"validated_fixes": []},
        timestamp=now,
        sequence=None,
        worker_attempt_id="attempt-1"
    )
    
    assert success is True
    
    cursor.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,))
    assert cursor.fetchone()[0] == "COMPLETED"

def test_stale_worker_rejected_on_completion(clean_db):
    task_id = "task-stale-complete"
    cursor = clean_db.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, repo_url, worker_attempt_id, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "RUNNING", "https://github.com/foo/bar", "attempt-new", now, now)
    )
    clean_db.commit()
    
    with pytest.raises(ValueError, match="Stale worker attempt"):
        JobManager.add_worker_event(
            task_id=task_id,
            status="COMPLETED",
            event_name="pipeline_complete",
            data={},
            timestamp=now,
            sequence=None,
            worker_attempt_id="attempt-OLD"
        )
