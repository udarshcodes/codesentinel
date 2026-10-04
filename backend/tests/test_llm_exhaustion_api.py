import pytest
import sqlite3
import json
import uuid
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import app
from fastapi.testclient import TestClient
from api.job_manager import JobManager, DB_PATH
import datetime

client = TestClient(app)

def test_llm_exhaustion_valid_request(monkeypatch):
    """
    Tests that a valid LLMExhaustionRequest returns 200 and correctly updates
    the database with WAITING_FOR_LLM_CAPACITY, next_retry, and atomic pipeline_state.
    """
    task_id = "test-llm-exh-" + str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    
    JobManager.create_job(task_id, "https://github.com/test/repo", commit_sha="test_commit_sha")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?", (attempt_id, task_id))
    conn.commit()
    conn.close()

    async def mock_validate(*args, **kwargs):
        return {"worker_attempt_id": attempt_id, "status": "RUNNING", "repo_url": "https://github.com/test/repo"}
    monkeypatch.setattr("api.worker_auth.validate_worker_attempt", mock_validate)

    payload = {
        "pipeline_state": {"current_stage": "AI_ANALYSIS"},
        "retry_count": 1,
        "next_retry": "2026-10-10T00:00:00Z", # will be overwritten by backend
        "model": "qwen/qwen3.6-27b",
        "error": "Rate limit exceeded",
        "reset_time": 600.0
    }
    
    response = client.post(
        f"/api/v1/job/{task_id}/llm-exhaustion", 
        json=payload,
        headers={"X-Worker-Attempt-Id": attempt_id}
    )
    
    assert response.status_code == 200, response.text
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state, next_retry FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "WAITING_FOR_LLM_CAPACITY"
    assert row[2] is not None
    
    state = json.loads(row[1])
    assert state["next_retry"] == row[2]
    assert state["retry_count"] == 1

def test_llm_exhaustion_stale_worker(monkeypatch):
    """
    Tests that a stale worker attempt ID is correctly rejected with 409 and does NOT mutate state.
    """
    task_id = "test-llm-stale-" + str(uuid.uuid4())
    stale_attempt_id = str(uuid.uuid4())
    active_attempt_id = str(uuid.uuid4())
    
    JobManager.create_job(task_id, "https://github.com/test/repo", commit_sha="test_commit_sha")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?", (active_attempt_id, task_id))
    conn.commit()
    conn.close()
    
    from fastapi import HTTPException
    async def mock_strict_validate(request, t_id):
        header_attempt = request.headers.get("X-Worker-Attempt-Id")
        if header_attempt != active_attempt_id:
            raise HTTPException(status_code=409, detail="Stale worker attempt (header mismatch)")
        return {"worker_attempt_id": active_attempt_id, "status": "RUNNING", "repo_url": "https://github.com/test/repo"}
    monkeypatch.setattr("api.worker_auth.validate_worker_attempt", mock_strict_validate)
    
    payload = {
        "pipeline_state": {},
        "retry_count": 0,
        "next_retry": "2026-10-10T00:00:00Z",
        "model": "qwen",
        "error": "exhausted"
    }
    
    response = client.post(
        f"/api/v1/job/{task_id}/llm-exhaustion", 
        json=payload,
        headers={"X-Worker-Attempt-Id": stale_attempt_id}
    )
    
    assert response.status_code == 409
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "RUNNING"

def test_llm_exhaustion_malformed_schema(monkeypatch):
    """
    Tests that a malformed schema (e.g. missing error field, invalid retry_count) is rejected with 422.
    """
    task_id = "test-llm-schema-" + str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    
    async def mock_validate(*args, **kwargs):
        return {"worker_attempt_id": attempt_id, "status": "RUNNING", "repo_url": "https://github.com/test/repo"}
    monkeypatch.setattr("api.worker_auth.validate_worker_attempt", mock_validate)

    payload = {
        "pipeline_state": {},
        "retry_count": -1, # INVALID (ge=0)
        "next_retry": "2026-10-10T00:00:00Z",
        "model": "qwen",
        "error": "" # INVALID (min_length=1)
    }
    
    response = client.post(
        f"/api/v1/job/{task_id}/llm-exhaustion", 
        json=payload,
        headers={"X-Worker-Attempt-Id": attempt_id}
    )
    
    assert response.status_code == 422
