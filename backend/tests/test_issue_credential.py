import pytest
import sqlite3
import json
import uuid
from datetime import datetime, timezone, timedelta
import hashlib
from fastapi.testclient import TestClient

from main import app
from api.job_manager import DB_PATH

@pytest.fixture
def client():
    return TestClient(app)

def setup_job(task_id, p_state, view_token="view123", worker_attempt_id="worker1"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    hashed_view = hashlib.sha256(view_token.encode()).hexdigest()
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, updated_at, pipeline_state, view_token, worker_attempt_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_id, "https://github.com/foo/bar", "WAITING_FOR_APPROVAL", now, json.dumps(p_state), hashed_view, worker_attempt_id)
    )
    conn.commit()
    conn.close()

def get_job_state(task_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT pipeline_state FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else None

def get_active_credentials(task_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT credential_id, token_hash, status, expires_at FROM approval_credentials WHERE task_id = ? AND status = 'active'", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def test_issue_credential_success(client):
    task_id = "test-issue-succ-" + str(uuid.uuid4())
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "cycle1",
        "approval_payload": {"fix_id": "fix1"},
        "repair_plan": [{"fix_id": "fix1", "status": "pending"}]
    }
    setup_job(task_id, p_state)

    res = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    if res.status_code != 200:
        print(f"ERROR PAYLOAD: {res.text}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "issued"
    assert "approval_token" in data
    assert data["approval_cycle_id"] == "cycle1"
    assert data["fix_id"] == "fix1"

    # Verify no state mutation
    new_state = get_job_state(task_id)
    assert new_state == p_state

    # Verify 1 active credential
    creds = get_active_credentials(task_id)
    assert len(creds) == 1

def test_issue_credential_existing_active(client):
    task_id = "test-issue-exist-" + str(uuid.uuid4())
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "cycle2",
        "approval_payload": {"fix_id": "fix2"},
        "repair_plan": [{"fix_id": "fix2", "status": "pending"}]
    }
    setup_job(task_id, p_state)

    # First issue
    res1 = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "issued"

    # Second issue
    res2 = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "active"
    assert data2.get("approval_token") is None # Should be absent or null

    creds = get_active_credentials(task_id)
    assert len(creds) == 1 # Still only one active credential

def test_issue_credential_missing_context(client):
    task_id = "test-issue-miss-" + str(uuid.uuid4())
    p_state = {
        "awaiting_approval": False, # NOT awaiting approval
        "approval_cycle_id": "cycle3",
        "approval_payload": {"fix_id": "fix3"}
    }
    setup_job(task_id, p_state)

    res = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    assert res.status_code == 400
    assert "Pipeline is not awaiting approval" in res.json()["detail"]

    creds = get_active_credentials(task_id)
    assert len(creds) == 0

def test_recover_credential(client):
    task_id = "test-recover-" + str(uuid.uuid4())
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "cycle4",
        "approval_payload": {"fix_id": "fix4"},
        "repair_plan": [{"fix_id": "fix4", "status": "pending"}]
    }
    setup_job(task_id, p_state)

    # Issue first token
    res1 = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    data1 = res1.json()

    # Recover token
    res2 = client.post(
        f"/api/v1/job/{task_id}/recover-credential", 
        json={"approval_cycle_id": "cycle4", "fix_id": "fix4"}, 
        headers={"Authorization": "Bearer view123"}
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "recovered"
    assert "approval_token" in data2
    assert data1["approval_token"] != data2["approval_token"]

    # Verify only 1 active credential exists
    creds = get_active_credentials(task_id)
    assert len(creds) == 1

    # Verify DB state untouched
    new_state = get_job_state(task_id)
    assert new_state == p_state
