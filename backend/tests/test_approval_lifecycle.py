import uuid
import pytest
import sqlite3
import os
import sys
import json
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from api.job_manager import JobManager, DB_PATH

@pytest.fixture(autouse=True)
def setup_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id LIKE 'test_lifecycle_%'")
    cursor.execute("DELETE FROM approval_credentials WHERE task_id LIKE 'test_lifecycle_%'")
    cursor.execute("DELETE FROM job_events WHERE task_id LIKE 'test_lifecycle_%'")
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id LIKE 'test_lifecycle_%'")
    cursor.execute("DELETE FROM approval_credentials WHERE task_id LIKE 'test_lifecycle_%'")
    cursor.execute("DELETE FROM job_events WHERE task_id LIKE 'test_lifecycle_%'")
    conn.commit()
    conn.close()

def _create_mock_job(task_id, fixes, current_fix_index=0):
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    expires_at = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + 3600, tz=timezone.utc).isoformat()
    
    pipeline_state = {
        "status": "WAITING_FOR_APPROVAL",
        "awaiting_approval": True,
        "approval_state": "pending",
        "repair_plan": fixes,
        "approval_payload": {"fix_id": fixes[current_fix_index]["fix_id"]} if current_fix_index < len(fixes) else None,
        "approval_cycle_id": "cycle_mock"
    }
    
    cursor.execute("""
        INSERT INTO jobs (task_id, repo_url, status, pipeline_state, worker_attempt_id)
        VALUES (?, ?, ?, ?, ?)
    """, (task_id, 'http://repo', 'WAITING_FOR_APPROVAL', json.dumps(pipeline_state), 'worker123'))
    
    cursor.execute("""
        INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?)
    """, (str(uuid.uuid4()), 'cycle_mock', task_id, pipeline_state["approval_payload"]["fix_id"] if pipeline_state["approval_payload"] else "fix1", 'hash_mock', expires_at))
    conn.commit()
    conn.close()

def test_single_high_risk_approval():
    fixes = [{"fix_id": "fix1", "risk_level": "high-risk", "status": "pending"}]
    _create_mock_job("test_lifecycle_single_app", fixes)
    
    JobManager.resolve_approval("test_lifecycle_single_app", "approved", "hash_mock", "fix1", "cycle_mock")
    
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = 'test_lifecycle_single_app'")
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "WAITING_FOR_DISPATCH"
    state = json.loads(row[1])
    assert state["awaiting_approval"] is False
    assert state["repair_plan"][0]["status"] == "approved"
    assert len(state["resolved_approvals"]) == 1
    assert state["resolved_approvals"][0]["fix_id"] == "fix1"
    assert "approval_payload" not in state or state["approval_payload"] is None

def test_single_high_risk_rejection():
    fixes = [{"fix_id": "fix1", "risk_level": "high-risk", "status": "pending"}]
    _create_mock_job("test_lifecycle_single_rej", fixes)
    
    JobManager.resolve_approval("test_lifecycle_single_rej", "rejected", "hash_mock", "fix1", "cycle_mock")
    
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = 'test_lifecycle_single_rej'")
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "NEEDS_REVIEW"
    state = json.loads(row[1])
    assert state["repair_plan"][0]["status"] == "rejected"

def test_multiple_high_risk_fixes_flow():
    fixes = [
        {"fix_id": "fix1", "risk_level": "high-risk", "status": "pending"},
        {"fix_id": "fix2", "risk_level": "high-risk", "status": "pending"}
    ]
    _create_mock_job("test_lifecycle_multi", fixes)
    
    # Approve first fix
    JobManager.resolve_approval("test_lifecycle_multi", "approved", "hash_mock", "fix1", "cycle_mock")
    
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = 'test_lifecycle_multi'")
    row = cursor.fetchone()
    conn.close()
    
    state = json.loads(row[1])
    assert state["repair_plan"][0]["status"] == "approved"
    assert state["repair_plan"][1]["status"] == "pending"
    assert len(state["resolved_approvals"]) == 1

def test_fix_id_mismatch():
    fixes = [{"fix_id": "fix1", "risk_level": "high-risk", "status": "pending"}]
    _create_mock_job("test_lifecycle_mismatch", fixes)
    
    with pytest.raises(ValueError, match="fix_id mismatch"):
        JobManager.resolve_approval("test_lifecycle_mismatch", "approved", "hash_mock", "wrong_id", "cycle_mock")

def test_stale_approval_token():
    fixes = [{"fix_id": "fix1", "risk_level": "high-risk", "status": "pending"}]
    _create_mock_job("test_lifecycle_stale_tok", fixes)
    
    # First use
    JobManager.resolve_approval("test_lifecycle_stale_tok", "approved", "hash_mock", "fix1", "cycle_mock")
    
    # Reuse token
    with pytest.raises(ValueError, match="Task is not in a state that can be approved"):
        JobManager.resolve_approval("test_lifecycle_stale_tok", "approved", "hash_mock", "fix1", "cycle_mock")

def test_waiting_for_approval_cannot_become_running():
    fixes = [{"fix_id": "fix1", "risk_level": "high-risk", "status": "pending"}]
    _create_mock_job("test_lifecycle_race", fixes)
    
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state("test_lifecycle_race", "worker123", "RUNNING", {})

def test_fix_status_transitions():
    fixes = [{"fix_id": "fix1", "risk_level": "high-risk", "status": "pending"}]
    _create_mock_job("test_lifecycle_fix_trans", fixes)
    
    # pending -> approved
    JobManager.resolve_approval("test_lifecycle_fix_trans", "approved", "hash_mock", "fix1", "cycle_mock")
    
    # Try approved -> rejected (should fail on "Approval already resolved" because the job level token is used)
    # Wait, the job token is used, so it fails on token reuse before checking the fix status.
    # But if we inject a new token for the same task and same fix_id:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    import json
    from datetime import datetime, timezone, timedelta
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    p_state = {"awaiting_approval": True, "approval_state": "pending", "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "approved"}], "approval_cycle_id": "cycle_mock_2"}
    cursor.execute("UPDATE jobs SET status = 'WAITING_FOR_APPROVAL', pipeline_state = ? WHERE task_id = 'test_lifecycle_fix_trans'", (json.dumps(p_state),))
    cursor.execute("INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at) VALUES (?, ?, ?, ?, ?, 'active', ?)", (str(uuid.uuid4()), "cycle_mock_2", "test_lifecycle_fix_trans", "fix1", "hash_mock", expires_at))
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="Fix fix1 is not pending"):
        JobManager.resolve_approval("test_lifecycle_fix_trans", "rejected", "hash_mock", "fix1", "cycle_mock_2")
