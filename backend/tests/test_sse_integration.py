import pytest
from fastapi.testclient import TestClient
import sqlite3
import hashlib
import uuid
import hmac
from api.job_manager import JobManager, DB_PATH
from main import app

client = TestClient(app)

@pytest.fixture
def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM sse_capabilities")
    conn.commit()
    conn.close()
    yield

def test_stream_capability_flow(setup_db):
    task_id = "test-cap-123"
    raw_token = "secret_token_456"
    hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, view_token) VALUES (?, ?, ?, ?)",
        (task_id, "https://github.com/foo/bar", "QUEUED", hashed_token)
    )
    conn.commit()
    conn.close()

    # 1. Missing capability / Invalid token
    resp = client.get(f"/api/v1/job/{task_id}/stream-capability")
    assert resp.status_code == 401
    
    # 2. Valid token
    resp = client.get(f"/api/v1/job/{task_id}/stream-capability", headers={"Authorization": f"Bearer {raw_token}"})
    assert resp.status_code == 200
    capability = resp.json().get("capability")
    assert capability is not None
    assert "ADMIN_SECRET" not in resp.text
    assert raw_token not in resp.text
    
    # 3. Stream with missing capability
    resp = client.get(f"/api/v1/stream?task_id={task_id}")
    assert resp.status_code == 401

    # 4. Stream with valid capability
    # The client blocks because it's a generator, we can test validation with a short timeout or directly use the db
    assert JobManager.validate_sse_capability(capability, task_id) is True
    
    # 5. Capability is single-use
    assert JobManager.validate_sse_capability(capability, task_id) is False

def test_three_consecutive_reconnects(setup_db):
    task_id = "test-reconnect-123"
    raw_token = "secret"
    hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, view_token) VALUES (?, ?, ?, ?)",
        (task_id, "foo", "QUEUED", hashed_token)
    )
    conn.commit()
    conn.close()

    for _ in range(3):
        resp = client.get(f"/api/v1/job/{task_id}/stream-capability", headers={"Authorization": f"Bearer {raw_token}"})
        assert resp.status_code == 200
        capability = resp.json()["capability"]
        assert JobManager.validate_sse_capability(capability, task_id) is True
        assert JobManager.validate_sse_capability(capability, task_id) is False
