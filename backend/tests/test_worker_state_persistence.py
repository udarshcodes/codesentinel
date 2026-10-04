import pytest
import sqlite3
import json
import uuid
import datetime
import httpx
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import app
from fastapi.testclient import TestClient
from api.job_manager import JobManager, DB_PATH

client = TestClient(app)

def _get_worker_auth_headers(task_id: str, worker_attempt_id: str):
    import hmac
    import hashlib
    timestamp = str(datetime.datetime.now(datetime.timezone.utc).timestamp())
    msg = f"POST:/api/v1/job/{task_id}/state:{task_id}:{timestamp}:"
    
    # We must patch the environment or test with an empty secret to bypass HMAC in test,
    # or actually compute the HMAC with a dummy secret.
    import os
    secret = os.environ.get("WORKER_WEBHOOK_SECRET", "")
    
    headers = {
        "X-Worker-Attempt-Id": worker_attempt_id,
        "X-Repo-Url": "https://github.com/test/test",
        "X-Timestamp": timestamp
    }
    
    if secret:
        # Since the request payload is hashed as well, we need to pass the body bytes in.
        # But this function doesn't take body bytes. We'll bypass full HMAC in tests if we mock validate_worker_attempt
        pass
        
    return headers

def test_worker_state_persistence_argument_order(monkeypatch):
    """
    Tests that POST /api/v1/job/{task_id}/state strictly maps keyword arguments 
    and avoids the P0 TypeError: save_worker_state() got multiple values for argument 'worker_attempt_id'
    """
    task_id = "test-arg-order-" + str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    
    JobManager.create_job(task_id, "https://github.com/test/repo", commit_sha="test_commit_sha")
    
    # Manually dispatch to get an attempt ID
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'DISPATCHING', worker_attempt_id = ? WHERE task_id = ?", (attempt_id, task_id))
    conn.commit()
    conn.close()

    # Mock validate_worker_attempt to bypass HMAC validation
    async def mock_validate(*args, **kwargs):
        return {"worker_attempt_id": attempt_id, "status": "DISPATCHING", "repo_url": "https://github.com/test/repo"}
    monkeypatch.setattr("api.worker_auth.validate_worker_attempt", mock_validate)

    payload = {
        "status": "RUNNING",
        "pipeline_state": {"current_stage": "AI_ANALYSIS"}
    }
    
    response = client.post(
        f"/api/v1/job/{task_id}/state", 
        json=payload,
        headers={"X-Worker-Attempt-Id": attempt_id}
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    assert response.json()["status"] == "ok"
    
    # Verify jobs.status and pipeline_state were updated atomically
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == "RUNNING"
    state_json = json.loads(row[1])
    assert state_json["current_stage"] == "AI_ANALYSIS"

def test_stale_worker_state_rejection(monkeypatch):
    """
    Tests that a stale worker attempt ID is correctly rejected with 409 and does NOT mutate state.
    """
    task_id = "test-stale-worker-" + str(uuid.uuid4())
    stale_attempt_id = str(uuid.uuid4())
    active_attempt_id = str(uuid.uuid4())
    
    JobManager.create_job(task_id, "https://github.com/test/repo", commit_sha="test_commit_sha")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # The DB expects active_attempt_id, but the stale worker uses stale_attempt_id
    cursor.execute("UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?", (active_attempt_id, task_id))
    conn.commit()
    conn.close()
    
    # Mock validate_worker_attempt returning the ACTIVE attempt (because it fetches from the DB)
    from fastapi import HTTPException
    async def mock_strict_validate(request, t_id):
        header_attempt = request.headers.get("X-Worker-Attempt-Id")
        if header_attempt != active_attempt_id:
            raise HTTPException(status_code=409, detail="Stale worker attempt (header mismatch)")
        return {"worker_attempt_id": active_attempt_id, "status": "RUNNING", "repo_url": "https://github.com/test/repo"}
    
    monkeypatch.setattr("api.worker_auth.validate_worker_attempt", mock_strict_validate)
    
    payload = {
        "status": "COMPLETED",
        "pipeline_state": {"current_stage": "CREATING_PULL_REQUEST"}
    }
    
    response = client.post(
        f"/api/v1/job/{task_id}/state", 
        json=payload,
        headers={"X-Worker-Attempt-Id": stale_attempt_id}
    )
    
    assert response.status_code == 409
    
    # Verify state was NOT updated
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "RUNNING"
    assert row[1] is None or json.loads(row[1]).get("current_stage") != "CREATING_PULL_REQUEST"
