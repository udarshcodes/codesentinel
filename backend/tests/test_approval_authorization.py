import pytest
import sqlite3
import uuid
import json
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

def setup_approval_job(task_id: str, worker_id: str) -> tuple[str, str]:
    """Sets up a job in WAITING_FOR_APPROVAL state."""
    cycle_id = "cycle-1"
    fix_id = "fix-1"
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_decision": None,
        "approval_cycle_id": cycle_id,
        "approval_payload": {"fix_id": fix_id},
        "repair_plan": [{"fix_id": fix_id, "status": "pending"}]
    }
    
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

def test_worker_cannot_approve(clean_db):
    task_id = "test-worker-auth-1"
    worker_id = "w1"
    cycle_id, fix_id = setup_approval_job(task_id, worker_id)
    
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "decision": "approved",
        "fix_id": fix_id,
        "approval_cycle_id": cycle_id
    }
    
    with pytest.raises(ValueError, match="Worker is not authorized to emit approval_resolved events"):
        JobManager.add_worker_event(
            task_id=task_id,
            worker_attempt_id=worker_id,
            status="WAITING_FOR_DISPATCH",
            event_name="approval_resolved",
            data=data,
            timestamp=now
        )
        
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    assert job["pipeline_state"]["approval_decision"] is None

def test_worker_cannot_reject(clean_db):
    task_id = "test-worker-auth-2"
    worker_id = "w1"
    cycle_id, fix_id = setup_approval_job(task_id, worker_id)
    
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "decision": "rejected",
        "fix_id": fix_id,
        "approval_cycle_id": cycle_id
    }
    
    with pytest.raises(ValueError, match="Worker is not authorized to emit approval_resolved events"):
        JobManager.add_worker_event(
            task_id=task_id,
            worker_attempt_id=worker_id,
            status="NEEDS_REVIEW",
            event_name="approval_resolved",
            data=data,
            timestamp=now
        )
        
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    assert job["pipeline_state"]["approval_decision"] is None

def test_resolve_approval_success(clean_db):
    task_id = "test-worker-auth-3"
    worker_id = "w1"
    cycle_id, fix_id = setup_approval_job(task_id, worker_id)
    
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
    
    res = JobManager.resolve_approval(task_id, "approved", token_hash, fix_id, cycle_id)
    
    assert res["status"] == "WAITING_FOR_DISPATCH"
    assert res["decision"] == "approved"
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_DISPATCH"
    assert job["pipeline_state"]["approval_decision"] == "approved"
    
    events = JobManager.get_events(task_id)
    approval_events = [e for e in events if e["event"] == "approval_resolved"]
    assert len(approval_events) == 1
    assert approval_events[0]["data"]["decision"] == "approved"

def test_stale_worker_cannot_approve(clean_db):
    task_id = "test-worker-auth-4"
    worker_id = "w1"
    cycle_id, fix_id = setup_approval_job(task_id, worker_id)
    
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "decision": "approved",
        "fix_id": fix_id,
        "approval_cycle_id": cycle_id
    }
    
    with pytest.raises(ValueError, match="Stale worker attempt"):
        JobManager.add_worker_event(
            task_id=task_id,
            worker_attempt_id="stale_worker_id",
            status="WAITING_FOR_DISPATCH",
            event_name="approval_resolved",
            data=data,
            timestamp=now
        )
