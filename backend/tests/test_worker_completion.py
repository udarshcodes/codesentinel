import pytest
import os
import json
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

@pytest.fixture
def clean_db():
    from api.job_manager import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM job_events")
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()
    yield

def test_valid_worker_pipeline_complete(clean_db):
    task_id = "task_complete_1"
    worker_attempt_id = "attempt_1"
    repo_url = "https://github.com/udarshcodes/portfolio"
    
    JobManager.create_job(task_id, repo_url)
    
    # Manually transition to RUNNING to simulate active worker
    from api.job_manager import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?",
        (worker_attempt_id, task_id)
    )
    conn.commit()
    
    # Emit pipeline_complete
    success, seq = JobManager.add_worker_event(
        task_id=task_id,
        worker_attempt_id=worker_attempt_id,
        status="COMPLETED",
        event_name="pipeline_complete",
        data={"confidence": 0.99},
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    assert success is True
    job = JobManager.get_job(task_id)
    assert job["status"] == "COMPLETED"

def test_stale_worker_pipeline_complete_rejected(clean_db):
    task_id = "task_complete_2"
    old_worker_id = "attempt_old"
    new_worker_id = "attempt_new"
    
    JobManager.create_job(task_id, "https://github.com/udarshcodes/portfolio")
    
    from api.job_manager import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?",
        (new_worker_id, task_id)  # Backend considers new_worker_id active
    )
    conn.commit()
    
    # Old worker tries to complete
    with pytest.raises(ValueError, match="Stale worker attempt"):
        JobManager.add_worker_event(
            task_id=task_id,
            worker_attempt_id=old_worker_id,
            status="COMPLETED",
            event_name="pipeline_complete",
            data={},
            timestamp=datetime.now(timezone.utc).isoformat()
        )

def test_save_state_refreshes_lease(clean_db):
    task_id = "task_complete_3"
    worker_id = "attempt_3"
    
    JobManager.create_job(task_id, "https://github.com/udarshcodes/portfolio")
    from api.job_manager import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ?, worker_heartbeat_at = ? WHERE task_id = ?",
        (worker_id, (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(), task_id)
    )
    conn.commit()
    
    # Save state should refresh heartbeat
    JobManager.save_worker_state(
        task_id, worker_id, "RUNNING", {"some_key": "val"}
    )
    
    job = JobManager.get_job(task_id)
    hb = datetime.fromisoformat(job["worker_heartbeat_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    # The heartbeat should be within the last few seconds, not 6 minutes ago
    assert (now - hb).total_seconds() < 10

def test_heartbeat_rejection_after_completion(clean_db, monkeypatch):
    monkeypatch.setenv("WORKER_WEBHOOK_SECRET", "test_secret")
    task_id = "task_complete_4"
    worker_id = "attempt_4"
    
    JobManager.create_job(task_id, "https://github.com/udarshcodes/portfolio")
    from api.job_manager import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status = 'COMPLETED', worker_attempt_id = ? WHERE task_id = ?",
        (worker_id, task_id)
    )
    conn.commit()
    
    # Simulate a heartbeat coming in after completion
    from api.worker_auth import validate_worker_attempt
    import asyncio
    
    async def mock_verify(*args, **kwargs):
        pass
    monkeypatch.setattr("api.worker_auth.verify_worker_signature", mock_verify)

    class MockRequest:
        def __init__(self):
            self.headers = {
                "X-Worker-Attempt-Id": worker_id,
                "X-Timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                "X-Repo-Url": "https://github.com/udarshcodes/portfolio"
            }
            class MockURL:
                path = f"/api/v1/job/{task_id}/heartbeat"
            self.url = MockURL()
            self.method = "POST"
        
        async def body(self):
            return b""
            
    # Should raise HTTPException 409 because task is no longer worker owned
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_worker_attempt(MockRequest(), task_id))
    
    assert exc.value.status_code == 409
    assert "Task is no longer worker owned" in exc.value.detail
