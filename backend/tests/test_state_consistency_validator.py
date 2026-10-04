import pytest
import sqlite3
import json
from api.job_manager import JobManager, DB_PATH

def test_validate_state_consistency_running_invalid():
    # RUNNING + awaiting_approval=true
    with pytest.raises(ValueError, match="RUNNING cannot claim awaiting_approval=True"):
        JobManager.validate_state_consistency(None, "t1", "RUNNING", {"awaiting_approval": True})
        
    # RUNNING + approval_state=pending
    with pytest.raises(ValueError, match="RUNNING cannot claim approval_state='pending'"):
        JobManager.validate_state_consistency(None, "t1", "RUNNING", {"approval_state": "pending"})

def test_validate_state_consistency_dispatch_invalid():
    # WAITING_FOR_DISPATCH + awaiting_approval=true
    with pytest.raises(ValueError, match="WAITING_FOR_DISPATCH cannot claim awaiting_approval=True"):
        JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_DISPATCH", {"awaiting_approval": True})
        
def test_validate_state_consistency_terminal_invalid():
    # NEEDS_REVIEW + awaiting_approval=true
    with pytest.raises(ValueError, match="Terminal state cannot claim awaiting_approval=True"):
        JobManager.validate_state_consistency(None, "t1", "NEEDS_REVIEW", {"awaiting_approval": True})

def test_validate_state_consistency_approval_invalid():
    # WAITING_FOR_APPROVAL + awaiting_approval=false
    with pytest.raises(ValueError, match="WAITING_FOR_APPROVAL requires awaiting_approval=True"):
        JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_APPROVAL", {})

    # WAITING_FOR_APPROVAL + missing approval_cycle_id
    with pytest.raises(ValueError, match="WAITING_FOR_APPROVAL requires approval_cycle_id"):
        JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_APPROVAL", {
            "awaiting_approval": True,
            "approval_state": "pending"
        })
        
    # WAITING_FOR_APPROVAL + missing approval_payload
    with pytest.raises(ValueError, match="WAITING_FOR_APPROVAL requires approval_payload"):
        JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_APPROVAL", {
            "awaiting_approval": True,
            "approval_state": "pending",
            "approval_cycle_id": "c1"
        })
        
    # WAITING_FOR_APPROVAL + missing fix_id
    with pytest.raises(ValueError, match="WAITING_FOR_APPROVAL requires approval_payload.fix_id"):
        JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_APPROVAL", {
            "awaiting_approval": True,
            "approval_state": "pending",
            "approval_cycle_id": "c1",
            "approval_payload": {}
        })

    # WAITING_FOR_APPROVAL + fix not in repair_plan
    with pytest.raises(ValueError, match="WAITING_FOR_APPROVAL requires fix_id in repair_plan"):
        JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_APPROVAL", {
            "awaiting_approval": True,
            "approval_state": "pending",
            "approval_cycle_id": "c1",
            "approval_payload": {"fix_id": "f1"},
            "repair_plan": []
        })

    # WAITING_FOR_APPROVAL + repair fix not pending
    with pytest.raises(ValueError, match="WAITING_FOR_APPROVAL requires repair_plan target fix status to be pending"):
        JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_APPROVAL", {
            "awaiting_approval": True,
            "approval_state": "pending",
            "approval_cycle_id": "c1",
            "approval_payload": {"fix_id": "f1"},
            "repair_plan": [{"fix_id": "f1", "status": "approved"}]
        })

def test_validate_state_consistency_valid_cases():
    # Should not raise any error
    JobManager.validate_state_consistency(None, "t1", "RUNNING", {"awaiting_approval": False})
    JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_DISPATCH", {"awaiting_approval": False})
    from datetime import datetime, timezone, timedelta
    valid_llm_state = {
        "awaiting_approval": False,
        "llm_waiting_state": True,
        "next_retry": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    }
    JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_LLM_CAPACITY", valid_llm_state)
    JobManager.validate_state_consistency(None, "t1", "COMPLETED", {"awaiting_approval": False})
    JobManager.validate_state_consistency(None, "t1", "FAILED", {"awaiting_approval": False})
    JobManager.validate_state_consistency(None, "t1", "NEEDS_REVIEW", {"awaiting_approval": False})
    
    JobManager.validate_state_consistency(None, "t1", "WAITING_FOR_APPROVAL", {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_cycle_id": "c1",
        "approval_payload": {"fix_id": "f1"},
        "repair_plan": [{"fix_id": "f1", "status": "pending"}]
    })

def test_validate_state_consistency_credential_mismatch():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-cred-mismatch"
    cursor.execute("INSERT OR REPLACE INTO jobs (task_id, repo_url, status) VALUES (?, 'a', 'RUNNING')", (task_id,))
    cursor.execute("INSERT OR REPLACE INTO approval_credentials (credential_id, task_id, approval_cycle_id, fix_id, token_hash, status) VALUES ('cred1', ?, 'old_cycle', 'old_fix', 'hash', 'active')", (task_id,))
    conn.commit()

    # Active credential cycle does not match
    with pytest.raises(ValueError, match="Active credential cycle_id does not match pipeline_state"):
        JobManager.validate_state_consistency(cursor, task_id, "WAITING_FOR_APPROVAL", {
            "awaiting_approval": True,
            "approval_state": "pending",
            "approval_cycle_id": "c1",
            "approval_payload": {"fix_id": "f1"},
            "repair_plan": [{"fix_id": "f1", "status": "pending"}]
        })
        
    cursor.execute("DELETE FROM approval_credentials WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
