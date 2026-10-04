import pytest
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from api.job_manager import JobManager, DB_PATH

def setup_test_job(task_id: str, status: str = "RUNNING", p_state: dict = None, attempt_id: str = "test-attempt"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    p_state_str = json.dumps(p_state) if p_state else None
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, pipeline_state, worker_attempt_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_id, "test", status, p_state_str, attempt_id, now, now)
    )
    conn.commit()
    conn.close()

def test_running_approval_required_reject():
    task_id = "test-event-consistency-1-" + str(uuid.uuid4())
    setup_test_job(task_id, "RUNNING")
    
    # Trying to send approval_required while in RUNNING
    with pytest.raises(ValueError, match="requires current status WAITING_FOR_APPROVAL"):
        JobManager.add_worker_event(
            task_id,
            status="WAITING_FOR_APPROVAL",
            event_name="approval_required",
            data={"fix_id": "1", "approval_cycle_id": "a"},
            worker_attempt_id="test-attempt",
            timestamp=datetime.now(timezone.utc).isoformat()
        )

def test_running_waiting_for_llm_reject():
    task_id = "test-event-consistency-2-" + str(uuid.uuid4())
    setup_test_job(task_id, "RUNNING")
    
    with pytest.raises(ValueError, match="requires current status WAITING_FOR_LLM_CAPACITY"):
        JobManager.add_worker_event(
            task_id,
            status="WAITING_FOR_LLM_CAPACITY",
            event_name="waiting_for_llm_capacity",
            data={"next_retry": "2025-01-01T00:00:00Z"},
            worker_attempt_id="test-attempt",
            timestamp=datetime.now(timezone.utc).isoformat()
        )

def test_waiting_for_approval_wrong_cycle_reject():
    task_id = "test-event-consistency-3-" + str(uuid.uuid4())
    p_state = {
        "approval_cycle_id": "correct-cycle",
        "approval_payload": {"fix_id": "correct-fix"},
        "awaiting_approval": True,
        "approval_state": "pending"
    }
    setup_test_job(task_id, "WAITING_FOR_APPROVAL", p_state)
    
    # Wrong cycle
    with pytest.raises(ValueError, match="approval_cycle_id mismatch"):
        JobManager.add_worker_event(
            task_id,
            status="WAITING_FOR_APPROVAL",
            event_name="approval_required",
            data={"fix_id": "correct-fix", "approval_cycle_id": "wrong-cycle"},
            worker_attempt_id="test-attempt",
            timestamp=datetime.now(timezone.utc).isoformat()
        )

def test_waiting_for_approval_accept():
    task_id = "test-event-consistency-4-" + str(uuid.uuid4())
    p_state = {
        "approval_cycle_id": "correct-cycle",
        "approval_payload": {"fix_id": "correct-fix"},
        "awaiting_approval": True,
        "approval_state": "pending"
    }
    setup_test_job(task_id, "WAITING_FOR_APPROVAL", p_state)
    
    # Correct identities
    success, _ = JobManager.add_worker_event(
        task_id,
        status="WAITING_FOR_APPROVAL",
        event_name="approval_required",
        data={"fix_id": "correct-fix", "approval_cycle_id": "correct-cycle"},
        worker_attempt_id="test-attempt",
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    assert success is True

def test_completed_pipeline_fake_completion():
    task_id = "test-event-consistency-5-" + str(uuid.uuid4())
    setup_test_job(task_id, "RUNNING")
    
    # A worker trying to append a pipeline_complete event while keeping the status as RUNNING
    with pytest.raises(ValueError, match="pipeline_complete requires event status COMPLETED"):
        JobManager.add_worker_event(
            task_id,
            status="RUNNING",
            event_name="pipeline_complete",
            data={},
            worker_attempt_id="test-attempt",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
