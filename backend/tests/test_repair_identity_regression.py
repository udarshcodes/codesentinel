import pytest
import sqlite3
import json
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from main import app
from api.job_manager import JobManager
from api.job_manager import DB_PATH

@pytest.fixture
def client():
    return TestClient(app)

def _create_job_state(task_id, repair_plan, approval_payload, cycle_id):
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_payload": approval_payload,
        "repair_plan": repair_plan,
        "approval_cycle_id": cycle_id
    }
    
    import hashlib
    view_token = "view123"
    hashed_view = hashlib.sha256(view_token.encode()).hexdigest()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, updated_at, pipeline_state, view_token) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "test_repo", "WAITING_FOR_APPROVAL", datetime.now(timezone.utc).isoformat(), json.dumps(p_state), hashed_view)
    )
    conn.commit()
    conn.close()

def _update_job_state(task_id, repair_plan, approval_payload, cycle_id):
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_payload": approval_payload,
        "repair_plan": repair_plan,
        "approval_cycle_id": cycle_id
    }
    
    cursor.execute(
        "UPDATE jobs SET pipeline_state = ?, status = 'WAITING_FOR_APPROVAL' WHERE task_id = ?",
        (json.dumps(p_state), task_id)
    )
    conn.commit()
    conn.close()

def test_regression_repair_plan_identity(client):
    task_id = "test-reg-id-" + str(uuid.uuid4())
    cycle_id = "cycle-prod-1"
    fix_id = "fix-prod-1"
    
    repair_plan = [{
        "fix_id": fix_id,
        "issue_id": "ISSUE-1",
        "issue_summary": "Test issue",
        "risk_level": "high-risk",
        "proposed_action": "Apply fix",
        "reasoning": "Test reasoning",
        "status": "pending"
    }]
    
    _create_job_state(task_id, repair_plan, {"fix_id": fix_id}, cycle_id)
    
    # 1. validate_approval_context succeeds
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    context = JobManager.validate_approval_context(cursor, task_id, cycle_id, fix_id, require_active_credential=False)
    conn.close()
    
    assert context is not None
    
    # 2. issue-approval-token succeeds
    res = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "issued"
    token = data["approval_token"]
    
    # 3. recover-credential succeeds
    res_rec = client.post(
        f"/api/v1/job/{task_id}/recover-credential", 
        json={"approval_cycle_id": cycle_id, "fix_id": fix_id},
        headers={"Authorization": "Bearer view123"}
    )
    assert res_rec.status_code == 200
    token2 = res_rec.json()["approval_token"]
    
    # 4. approve succeeds
    res_app = client.post(
        f"/api/v1/approve/{task_id}",
        json={"approval_token": token2, "decision": "approved", "fix_id": fix_id, "approval_cycle_id": cycle_id}
    )
    assert res_app.status_code == 200

def test_negative_id_test(client):
    task_id = "test-neg-id-" + str(uuid.uuid4())
    cycle_id = "cycle-neg-1"
    
    # Intentionally omitted fix_id, added id
    repair_plan = [{
        "id": "fix1",
        "issue_id": "ISSUE-1",
        "issue_summary": "Test issue",
        "risk_level": "high-risk",
        "proposed_action": "Apply fix",
        "reasoning": "Test reasoning",
        "status": "pending"
    }]
    
    _create_job_state(task_id, repair_plan, {"fix_id": "fix1"}, cycle_id)
    
    # Should fail validate_approval_context
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    with pytest.raises(ValueError, match="not found in repair plan"):
        JobManager.validate_approval_context(cursor, task_id, cycle_id, "fix1", require_active_credential=False)
    conn.close()
        
    # issue-approval-token should fail
    res = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    assert res.status_code == 400
    assert "not found in repair plan" in res.text

def test_multiple_fixes_canonical_flow(client):
    task_id = "test-multi-id-" + str(uuid.uuid4())
    cycle_id = "cycle-multi-1"
    
    repair_plan = [
        {"fix_id": "A", "status": "pending", "risk_level": "high-risk"},
        {"fix_id": "B", "status": "pending", "risk_level": "high-risk"},
        {"fix_id": "C", "status": "pending", "risk_level": "high-risk"}
    ]
    
    _create_job_state(task_id, repair_plan, {"fix_id": "A"}, cycle_id)
    
    # Issue token for A
    res_a = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_a = res_a.json()["approval_token"]
    
    # Approve A
    res_app_a = client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_a, "decision": "approved", "fix_id": "A", "approval_cycle_id": cycle_id})
    assert res_app_a.status_code == 200
    
    # Manually transition to B to simulate worker
    cycle_id_b = "cycle-multi-2"
    _update_job_state(task_id, [
        {"fix_id": "A", "status": "approved", "risk_level": "high-risk"},
        {"fix_id": "B", "status": "pending", "risk_level": "high-risk"},
        {"fix_id": "C", "status": "pending", "risk_level": "high-risk"}
    ], {"fix_id": "B"}, cycle_id_b)
    
    # Test Fix Level Rejection (Reject B)
    res_b = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_b = res_b.json()["approval_token"]
    
    res_app_b = client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_b, "decision": "rejected", "fix_id": "B", "approval_cycle_id": cycle_id_b})
    assert res_app_b.status_code == 200
    
    # Verify DB state for B rejection
    conn = sqlite3.connect(DB_PATH)
    state_str = conn.execute("SELECT pipeline_state FROM jobs WHERE task_id = ?", (task_id,)).fetchone()[0]
    conn.close()
    
    state = json.loads(state_str)
    rp = state["repair_plan"]
    assert rp[0]["fix_id"] == "A" and rp[0]["status"] == "approved"
    assert rp[1]["fix_id"] == "B" and rp[1]["status"] == "rejected"
    assert rp[2]["fix_id"] == "C" and rp[2]["status"] == "pending"

def test_cross_fix_protection(client):
    task_id = "test-cross-id-" + str(uuid.uuid4())
    cycle_id = "cycle-cross-1"
    
    repair_plan = [
        {"fix_id": "A", "status": "pending", "risk_level": "high-risk"},
        {"fix_id": "B", "status": "pending", "risk_level": "high-risk"}
    ]
    
    _create_job_state(task_id, repair_plan, {"fix_id": "A"}, cycle_id)
    
    # Issue token for A
    res_a = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_a = res_a.json()["approval_token"]
    
    # Attempt to use token A on fix B -> should fail because payload requires A
    res_fail1 = client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_a, "decision": "approved", "fix_id": "B", "approval_cycle_id": cycle_id})
    assert res_fail1.status_code == 400
    assert "fix_id mismatch" in res_fail1.text or "not found" in res_fail1.text or "Invalid" in res_fail1.text
    
    # Approve A properly
    res_app_a = client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_a, "decision": "approved", "fix_id": "A", "approval_cycle_id": cycle_id})
    assert res_app_a.status_code == 200
    
    # Manually transition to B
    cycle_id_b = "cycle-cross-2"
    _update_job_state(task_id, [
        {"fix_id": "A", "status": "approved", "risk_level": "high-risk"},
        {"fix_id": "B", "status": "pending", "risk_level": "high-risk"}
    ], {"fix_id": "B"}, cycle_id_b)
    
    # Issue token for B
    res_b = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_b = res_b.json()["approval_token"]
    
    # Attempt to use cycle A for fix B
    res_fail2 = client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_b, "decision": "approved", "fix_id": "B", "approval_cycle_id": cycle_id})
    assert res_fail2.status_code == 400
    assert "mismatch" in res_fail2.text.lower() or "not found" in res_fail2.text.lower() or "invalid" in res_fail2.text.lower()
