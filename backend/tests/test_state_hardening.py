import pytest
import sqlite3
import json
from datetime import datetime, timezone
import os

from api.job_manager import JobManager, DB_PATH

@pytest.fixture
def clean_db():
    # Make sure we have a fresh DB before each test if needed
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()
    yield

def test_event_spoofing_prevention(clean_db):
    """A worker submitting an event cannot force an invalid state transition."""
    task_id = "test_spoof_1"
    worker_id = "worker_123"
    
    JobManager.create_job(task_id, "https://github.com/test/test")
    # Manually set to RUNNING
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?", (worker_id, task_id))
    conn.commit()
    conn.close()

    # Attempt to spoof COMPLETED state without the legitimate transition via save_worker_state
    # (add_worker_event does use transition_job_state now, which enforces VALID_TRANSITIONS)
    # Actually wait, RUNNING -> COMPLETED is a valid transition in VALID_TRANSITIONS.
    # But does add_worker_event allow an arbitrary valid transition?
    # Yes, it routes through transition_job_state. 
    # But wait, we want to test that a non-valid transition is rejected.
    # Example: RUNNING -> WAITING_FOR_DISPATCH is not allowed via worker event. (Valid transitions from RUNNING: WAITING_FOR_APPROVAL, WAITING_FOR_LLM_CAPACITY, COMPLETED, FAILED, DISPATCHING).
    
    # Wait, if RUNNING to COMPLETED is a valid transition, is it allowed via add_worker_event? Yes, if the worker sends status="COMPLETED".
    # What is a truly invalid transition?
    # COMPLETED -> RUNNING
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'COMPLETED', worker_attempt_id = ? WHERE task_id = ?", (worker_id, task_id))
    conn.commit()
    conn.close()
    
    with pytest.raises(ValueError, match="Invalid state transition: COMPLETED -> RUNNING"):
        JobManager.add_worker_event(
            task_id,
            worker_id,
            "RUNNING",
            "agent_running",
            {},
            datetime.now(timezone.utc).isoformat()
        )
        
    # Verify state remains COMPLETED
    job = JobManager.get_job(task_id)
    assert job["status"] == "COMPLETED"

def test_event_state_divergence(clean_db):
    """If an event submission fails state validation, neither the jobs table nor the job_events table is modified."""
    task_id = "test_divergence_1"
    worker_id = "worker_123"
    
    JobManager.create_job(task_id, "https://github.com/test/test")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'WAITING_FOR_APPROVAL', worker_attempt_id = ? WHERE task_id = ?", (worker_id, task_id))
    conn.commit()
    conn.close()

    # WAITING_FOR_APPROVAL -> RUNNING is invalid
    try:
        JobManager.add_worker_event(
            task_id,
            worker_id,
            "RUNNING",
            "agent_complete",
            {},
            datetime.now(timezone.utc).isoformat()
        )
    except ValueError:
        pass
        
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    
    events = JobManager.get_events(task_id)
    assert len(events) == 0

def test_end_to_end_approval(clean_db):
    """RUNNING -> WAITING_FOR_APPROVAL -> approve -> WAITING_FOR_DISPATCH -> RUNNING"""
    task_id = "test_e2e_approval"
    worker_id = "worker_123"
    
    JobManager.create_job(task_id, "https://github.com/test/test")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?", (worker_id, task_id))
    conn.commit()
    conn.close()
    
    # 1. RUNNING -> WAITING_FOR_APPROVAL
    pipeline_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "cycle_1",
        "approval_payload": {"fix_id": "fix_1"},
        "repair_plan": [{"fix_id": "fix_1", "status": "pending"}]
    }
    
    # Needs a credential to exist for WAITING_FOR_APPROVAL validation
    import uuid
    import hashlib
    cred_id = str(uuid.uuid4())
    token = "secret_token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc).timestamp() + 3600)
    expires_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, worker_attempt_id) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
        (cred_id, task_id, "fix_1", "cycle_1", token_hash, "active", expires_iso, worker_id)
    )
    conn.commit()
    conn.close()
    
    success = JobManager.save_worker_state(task_id, worker_id, "WAITING_FOR_APPROVAL", pipeline_state)
    assert success is True
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    
    # 2. approve -> WAITING_FOR_DISPATCH
    result = JobManager.resolve_approval(task_id, "approved", token_hash, "fix_1", "cycle_1")
    assert result["status"] == "WAITING_FOR_DISPATCH"
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_DISPATCH"
    
    # Verify event was created
    events = JobManager.get_events(task_id)
    assert len(events) == 1
    assert events[0]["event"] == "approval_resolved"
    assert events[0]["status"] == "WAITING_FOR_DISPATCH"
    
    # 3. WAITING_FOR_DISPATCH -> RUNNING (via claim_waiting_job and dispatching)
    new_worker_id = JobManager.claim_waiting_job(task_id)
    assert new_worker_id is not None
    job = JobManager.get_job(task_id)
    assert job["status"] == "DISPATCHING"
    
    # Worker starts
    JobManager.add_worker_event(task_id, new_worker_id, "STARTING", "pipeline_started", {}, datetime.now(timezone.utc).isoformat())
    job = JobManager.get_job(task_id)
    assert job["status"] == "STARTING"
    events = JobManager.get_events(task_id)
    assert events[-1]["status"] == "STARTING"

def test_end_to_end_llm_waiting(clean_db):
    task_id = "test_llm_waiting"
    worker_id = "worker_123"
    
    JobManager.create_job(task_id, "https://github.com/test/test")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'RUNNING', worker_attempt_id = ? WHERE task_id = ?", (worker_id, task_id))
    conn.commit()
    conn.close()
    
    next_retry = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + 3600, tz=timezone.utc).isoformat()
    pipeline_state = {
        "last_llm_model": "test-model", "last_llm_error": "rate limited"
    }
    
    success = JobManager.set_worker_waiting_capacity(task_id, worker_id, next_retry, pipeline_state)
    assert success is True
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_LLM_CAPACITY"
    assert job["next_retry"] == next_retry
    
    events = JobManager.get_events(task_id)
    assert len(events) == 1
    assert events[0]["status"] == "WAITING_FOR_LLM_CAPACITY"
    assert events[0]["event"] == "waiting_for_llm_capacity"

def test_end_to_end_rejection(clean_db):
    task_id = "test_rejection"
    worker_id = "worker_123"
    
    JobManager.create_job(task_id, "https://github.com/test/test")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'WAITING_FOR_APPROVAL', worker_attempt_id = ? WHERE task_id = ?", (worker_id, task_id))
    
    pipeline_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "cycle_1",
        "approval_payload": {"fix_id": "fix_1"},
        "repair_plan": [{"fix_id": "fix_1", "status": "pending"}]
    }
    cursor.execute("UPDATE jobs SET pipeline_state = ? WHERE task_id = ?", (json.dumps(pipeline_state), task_id))
    
    import uuid
    import hashlib
    cred_id = str(uuid.uuid4())
    token = "secret_token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc).timestamp() + 3600)
    expires_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    
    cursor.execute(
        "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, worker_attempt_id) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
        (cred_id, task_id, "fix_1", "cycle_1", token_hash, "active", expires_iso, worker_id)
    )
    conn.commit()
    conn.close()
    
    # Reject -> NEEDS_REVIEW
    result = JobManager.resolve_approval(task_id, "rejected", token_hash, "fix_1", "cycle_1")
    assert result["status"] == "NEEDS_REVIEW"
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "NEEDS_REVIEW"
    
    # Verify no worker can resurrect it
    try:
        JobManager.add_worker_event(task_id, worker_id, "RUNNING", "pipeline_started", {}, datetime.now(timezone.utc).isoformat())
    except ValueError as e:
        assert "Invalid state transition" in str(e) or "pipeline_started requires" in str(e)
        
    job = JobManager.get_job(task_id)
    assert job["status"] == "NEEDS_REVIEW"
