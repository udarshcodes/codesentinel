import pytest
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager, DB_PATH

@pytest.fixture
def clean_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()
    yield

def test_resolve_approval_validates_credential(clean_db):
    """Verify resolve_approval enforces credential validation."""
    task_id = "test_app_reg_2"
    worker_id = "w1"
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "cycle_1",
        "approval_payload": {"fix_id": "fix_1"},
        "repair_plan": [
            {"fix_id": "fix_1", "approval_cycle_id": "cycle_1", "status": "pending"}
        ],
        "resolved_approvals": []
    }
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state) VALUES (?, ?, ?, ?)",
        (task_id, "WAITING_FOR_APPROVAL", worker_id, json.dumps(p_state))
    )
    conn.commit()
    conn.close()
    
    # Missing credential
    with pytest.raises(ValueError, match="Active approval credential not found"):
        JobManager.resolve_approval(task_id, "approved", "invalid_token", "fix_1", "cycle_1")
        
def test_resolve_approval_updates_repair_plan(clean_db):
    """Verify resolve_approval updates the repair_plan."""
    task_id = "test_app_reg_3"
    worker_id = "w1"
    fix_id = "fix_1"
    cycle_id = "cycle_1"
    
    # Setup job with valid repair_plan
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": cycle_id,
        "approval_payload": {"fix_id": fix_id},
        "repair_plan": [
            {
                "fix_id": fix_id,
                "description": "test fix",
                "status": "pending",
                "approval_cycle_id": cycle_id
            }
        ],
        "resolved_approvals": []
    }
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state) VALUES (?, ?, ?, ?)",
        (task_id, "WAITING_FOR_APPROVAL", worker_id, json.dumps(p_state))
    )
    
    import hashlib
    valid_token = "valid_token"
    token_hash = hashlib.sha256(valid_token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    cursor.execute(
        "INSERT INTO approval_credentials (task_id, approval_cycle_id, token_hash, expires_at, fix_id, status) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, cycle_id, token_hash, expires, fix_id, "active")
    )
    conn.commit()
    conn.close()
    
    res = JobManager.resolve_approval(task_id, "approved", token_hash, fix_id, cycle_id)
    assert res["status"] == "WAITING_FOR_DISPATCH" 
    assert res["decision"] == "approved"
    
    job = JobManager.get_job(task_id)
    state = job["pipeline_state"]
    assert state["repair_plan"][0]["status"] == "approved"
    assert len(state["resolved_approvals"]) == 1
    assert state["resolved_approvals"][0]["decision"] == "approved"
    assert state["resolved_approvals"][0]["fix_id"] == fix_id

def test_approval_resolved_event_contract(clean_db):
    """Verify approval_resolved event always contains approval_cycle_id, fix_id, decision."""
    task_id = "test_app_reg_4"
    worker_id = "w1"
    fix_id = "fix_4"
    cycle_id = "cycle_4"
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": cycle_id,
        "approval_payload": {"fix_id": fix_id},
        "repair_plan": [
            {
                "fix_id": fix_id,
                "description": "test fix",
                "status": "pending",
                "approval_cycle_id": cycle_id
            }
        ],
        "resolved_approvals": []
    }
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state) VALUES (?, ?, ?, ?)",
        (task_id, "WAITING_FOR_APPROVAL", worker_id, json.dumps(p_state))
    )
    
    import hashlib
    valid_token = "valid_token"
    token_hash = hashlib.sha256(valid_token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    cursor.execute(
        "INSERT INTO approval_credentials (task_id, approval_cycle_id, token_hash, expires_at, fix_id, status) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, cycle_id, token_hash, expires, fix_id, "active")
    )
    conn.commit()
    conn.close()
    
    JobManager.resolve_approval(task_id, "approved", token_hash, fix_id, cycle_id)
    
    events = JobManager.get_events(task_id, 0)
    resolved_event = next((e for e in events if e["event"] == "approval_resolved"), None)
    assert resolved_event is not None
    
    data = resolved_event["data"]
    assert data["decision"] == "approved"
    assert data["fix_id"] == fix_id
    assert data["approval_cycle_id"] == cycle_id
