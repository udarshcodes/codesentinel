import pytest
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from api.job_manager import JobManager, DB_PATH

@pytest.fixture
def clean_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()

def setup_approval_job(task_id: str, worker_id: str, p_state_overrides: dict = None) -> tuple[str, str]:
    cycle_id = "cycle-1"
    fix_id = "fix-1"
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_decision": None,
        "approval_cycle_id": cycle_id,
        "approval_payload": {"fix_id": fix_id, "data": "original"},
        "repair_plan": [{"fix_id": fix_id, "status": "pending"}]
    }
    if p_state_overrides:
        p_state.update(p_state_overrides)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "WAITING_FOR_APPROVAL", worker_id, json.dumps(p_state), now, now)
    )
    conn.commit()
    conn.close()
    
    return cycle_id, fix_id

def setup_running_job(task_id: str, worker_id: str) -> None:
    p_state = {
        "current_fix": None,
        "repair_plan": []
    }
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id, pipeline_state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "RUNNING", worker_id, json.dumps(p_state), now, now)
    )
    conn.commit()
    conn.close()

def setup_valid_credential(task_id: str, worker_id: str, fix_id: str, cycle_id: str) -> str:
    import hashlib
    raw_token = "valid_token_123"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    expires = (now + timedelta(minutes=15)).isoformat()
    
    cursor.execute(
        "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, worker_attempt_id) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
        (str(uuid.uuid4()), task_id, fix_id, cycle_id, token_hash, expires, now.isoformat(), worker_id)
    )
    conn.commit()
    conn.close()
    return token_hash

def test_a_worker_cannot_approve_through_state(clean_db):
    task_id = "test-auth-a"
    worker_id = "w1"
    setup_approval_job(task_id, worker_id)
    
    forged_state = {
        "awaiting_approval": False,
        "approval_state": "approved",
        "approval_decision": "approved",
        "approval_cycle_id": None,
        "approval_payload": None,
        "repair_plan": [{"fix_id": "fix-1", "status": "approved"}]
    }
    
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state(task_id, worker_id, "WAITING_FOR_DISPATCH", forged_state)
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    assert job["pipeline_state"]["approval_decision"] is None
    assert job["pipeline_state"]["repair_plan"][0]["status"] == "pending"

def test_b_worker_cannot_reject_through_state(clean_db):
    task_id = "test-auth-b"
    worker_id = "w1"
    setup_approval_job(task_id, worker_id)
    
    forged_state = {
        "awaiting_approval": False,
        "approval_state": "rejected",
        "approval_decision": "rejected",
    }
    
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state(task_id, worker_id, "NEEDS_REVIEW", forged_state)
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    assert job["pipeline_state"]["approval_decision"] is None

def test_c_worker_cannot_fail_pending_approval(clean_db):
    task_id = "test-auth-c"
    worker_id = "w1"
    setup_approval_job(task_id, worker_id)
    
    forged_state = {"error": "Some failure"}
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state(task_id, worker_id, "FAILED", forged_state)
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"

def test_d_worker_cannot_tamper_with_approval_payload(clean_db):
    task_id = "test-auth-d"
    worker_id = "w1"
    setup_approval_job(task_id, worker_id)
    
    forged_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "cycle-1",
        "approval_payload": {"fix_id": "fix-1", "data": "MALICIOUSLY_ALTERED"},
        "repair_plan": [{"fix_id": "fix-1", "status": "pending"}]
    }
    
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state(task_id, worker_id, "WAITING_FOR_APPROVAL", forged_state)
    
    job = JobManager.get_job(task_id)
    assert job["pipeline_state"]["approval_payload"]["data"] == "original"

def test_e_legitimate_transition_still_works(clean_db):
    task_id = "test-auth-e"
    worker_id = "w1"
    setup_running_job(task_id, worker_id)
    
    new_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_decision": None,
        "approval_cycle_id": "cycle-1",
        "approval_payload": {"fix_id": "fix-1", "data": "original"},
        "repair_plan": [{"fix_id": "fix-1", "status": "pending"}]
    }
    
    success = JobManager.save_worker_state(task_id, worker_id, "WAITING_FOR_APPROVAL", new_state)
    assert success is True
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    assert job["pipeline_state"]["awaiting_approval"] is True

def test_f_real_human_approval_still_works(clean_db):
    task_id = "test-auth-f"
    worker_id = "w1"
    cycle_id, fix_id = setup_approval_job(task_id, worker_id)
    token_hash = setup_valid_credential(task_id, worker_id, fix_id, cycle_id)
    
    res = JobManager.resolve_approval(task_id, "approved", token_hash, fix_id, cycle_id)
    assert res["status"] == "WAITING_FOR_DISPATCH"
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_DISPATCH"
    assert job["pipeline_state"]["approval_decision"] == "approved"
    
    # Credential should be used
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM approval_credentials WHERE token_hash = ?", (token_hash,))
    cred_status = cursor.fetchone()[0]
    conn.close()
    assert cred_status == "used"

def test_g_explicit_exploit_payload(clean_db):
    task_id = "test-auth-g"
    worker_id = "w1"
    setup_approval_job(task_id, worker_id)
    
    forged_state = {
        "awaiting_approval": False,
        "approval_state": None,
        "approval_decision": None,
        "approval_cycle_id": None,
        "approval_payload": None,
        "repair_plan": [{"fix_id": "fix-1", "status": "pending"}],
    }
    
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state(
            task_id,
            worker_id,
            "WAITING_FOR_DISPATCH",
            forged_state,
        )
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    assert job["pipeline_state"]["awaiting_approval"] is True
