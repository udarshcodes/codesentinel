import asyncio
import sqlite3
import pytest
import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from api.job_manager import JobManager, DB_PATH
from main import app

@pytest.fixture(autouse=True)
def setup_teardown():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM approval_credentials")
    cursor.execute("DELETE FROM job_events")
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM approval_credentials")
    cursor.execute("DELETE FROM job_events")
    conn.commit()
    conn.close()

def test_recovery_vs_stale_worker():
    client = TestClient(app)
    task_id = str(uuid.uuid4())
    cycle_id = str(uuid.uuid4())
    fix_id = "fix-a"
    stale_worker_id = "worker-attempt-A"
    current_worker_id = "worker-attempt-B"
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    
    # Setup job with active worker B, but active credential belongs to stale worker A
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": cycle_id,
        "approval_payload": {"fix_id": fix_id},
        "repair_plan": [{"fix_id": fix_id, "status": "pending"}]
    }
    
    import hashlib
    view_token = "view-token-123"
    hashed_token = hashlib.sha256(view_token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state, view_token) VALUES (?, ?, ?, ?, ?)",
        (task_id, "WAITING_FOR_APPROVAL", current_worker_id, json.dumps(p_state), hashed_token)
    )
    cursor.execute(
        "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, status, expires_at, worker_attempt_id) VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (str(uuid.uuid4()), task_id, fix_id, cycle_id, expires, stale_worker_id)
    )
    conn.commit()
    conn.close()

    # Recovery request (simulating stale worker trying to recover because it still thinks it owns the credential)
    # Actually, the user asks for recovery authorization bound to current worker. The credential recovery endpoint
    # will check if active_cred_worker_attempt_id != current_worker_id and raise an exception.
    response = client.post(
        f"/api/v1/job/{task_id}/recover-credential",
        json={"approval_cycle_id": cycle_id, "fix_id": fix_id},
        headers={"Authorization": "Bearer view-token-123"}
    )
    assert response.status_code == 400
    assert "Stale worker attempt detected during recovery" in response.json()["detail"]
    
def test_recovery_vs_resolved_approval():
    client = TestClient(app)
    task_id = str(uuid.uuid4())
    cycle_id = str(uuid.uuid4())
    fix_id = "fix-a"
    current_worker_id = "worker-attempt-B"
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    
    # Setup job that is ALREADY resolved
    p_state = {
        "awaiting_approval": False, # Resolved
        "approval_state": "approved", # Resolved
        "approval_cycle_id": cycle_id,
        "approval_payload": {"fix_id": fix_id},
        "repair_plan": [{"fix_id": fix_id, "status": "approved"}]
    }
    
    import hashlib
    view_token = "view-token-123"
    hashed_token = hashlib.sha256(view_token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state, view_token) VALUES (?, ?, ?, ?, ?)",
        (task_id, "WAITING_FOR_DISPATCH", current_worker_id, json.dumps(p_state), hashed_token)
    )
    conn.commit()
    conn.close()

    response = client.post(
        f"/api/v1/job/{task_id}/recover-credential",
        json={"approval_cycle_id": cycle_id, "fix_id": fix_id},
        headers={"Authorization": "Bearer view-token-123"}
    )
    assert response.status_code == 400
    assert "Task is not in a state that can be approved" in response.json()["detail"]
    
@pytest.mark.asyncio
async def test_concurrent_recovery():
    """Verify concurrent recovery requests to prevent duplicate active credentials."""
    task_id = str(uuid.uuid4())
    cycle_id = str(uuid.uuid4())
    fix_id = "fix-a"
    current_worker_id = "worker-attempt-B"
    cycle_id = "cycle_recovery"
    fix_id = "fix-a"
    current_worker_id = "worker-attempt-B"
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_payload": {"fix_id": fix_id},
        "repair_plan": [{"id": fix_id, "status": "pending"}],
        "approval_cycle_id": "cycle_recovery"
    }
    
    import hashlib
    view_token = "view-token-123"
    hashed_token = hashlib.sha256(view_token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state, view_token) VALUES (?, ?, ?, ?, ?)",
        (task_id, "WAITING_FOR_APPROVAL", current_worker_id, json.dumps(p_state), hashed_token)
    )
    cursor.execute(
        "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, status, expires_at, worker_attempt_id) VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (str(uuid.uuid4()), task_id, fix_id, cycle_id, expires, current_worker_id)
    )
    conn.commit()
    conn.close()

    async def try_recover():
        client = TestClient(app)
        loop = asyncio.get_running_loop()
        def _post():
            return client.post(
                f"/api/v1/job/{task_id}/recover-credential",
                json={"approval_cycle_id": cycle_id, "fix_id": fix_id},
                headers={"Authorization": "Bearer view-token-123"}
            )
        return await loop.run_in_executor(None, _post)

    results = await asyncio.gather(
        try_recover(),
        try_recover(),
        try_recover()
    )
    
    successes = [r for r in results if r.status_code == 200]
    errors = [r for r in results if r.status_code != 200]
    
    # Even if they execute sequentially via TestClient under the hood, 
    # atomicity ensures only 1 active credential exists at the end.
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM approval_credentials WHERE status = 'active' AND task_id = ?", (task_id,))
    active_count = cursor.fetchone()[0]
    conn.close()
    
    assert active_count == 1, f"Expected exactly 1 active credential after concurrent recoveries, found {active_count}"
