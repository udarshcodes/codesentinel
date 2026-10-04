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
    cursor.execute("DELETE FROM jobs WHERE task_id = 'test_approval_multiple'")
    cursor.execute("DELETE FROM approval_credentials WHERE task_id = 'test_approval_multiple'")
    cursor.execute("DELETE FROM job_events WHERE task_id = 'test_approval_multiple'")
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = 'test_approval_multiple'")
    cursor.execute("DELETE FROM approval_credentials WHERE task_id = 'test_approval_multiple'")
    cursor.execute("DELETE FROM job_events WHERE task_id = 'test_approval_multiple'")
    conn.commit()
    conn.close()

def test_approval_contract_multiple_fixes():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    # 1. Setup job
    now = datetime.now(timezone.utc).isoformat()
    
    pipeline_state = {
        "status": "WAITING_FOR_APPROVAL",
        "awaiting_approval": True,
        "approval_state": "pending",
        "repair_plan": [
            {
                "fix_id": "fix123",
                "risk_level": "high-risk",
                "status": "pending"
            },
            {
                "fix_id": "fix456",
                "risk_level": "high-risk",
                "status": "pending"
            }
        ],
        "approval_payload": {
            "fix_id": "fix123",
            "risk_level": "high-risk"
        },
        "approval_cycle_id": "cycle123"
    }
    
    expires_at = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + 3600, tz=timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO jobs (task_id, repo_url, status, pipeline_state, worker_attempt_id)
        VALUES (?, ?, ?, ?, ?)
    """, ('test_approval_multiple', 'http://repo', 'WAITING_FOR_APPROVAL', json.dumps(pipeline_state), 'worker123'))
    
    import uuid
    cursor.execute("""
        INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?)
    """, (str(uuid.uuid4()), 'cycle123', 'test_approval_multiple', 'fix123', 'hash_mock', expires_at))
    
    conn.commit()
    conn.close()
    
    # 2. Try to overwrite status using heartbeat (save_worker_state simulating RUNNING)
    # The fix to save_worker_state should prevent RUNNING from overwriting WAITING_FOR_APPROVAL
    import pytest
    with pytest.raises(ValueError, match="Worker state persistence is forbidden while human approval is pending"):
        JobManager.save_worker_state('test_approval_multiple', 'worker123', 'RUNNING', pipeline_state)
    
    # Verify status is still WAITING_FOR_APPROVAL
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM jobs WHERE task_id = 'test_approval_multiple'")
    assert cursor.fetchone()[0] == 'WAITING_FOR_APPROVAL'
    conn.close()
    
    # 3. Resolve Approval
    import hashlib
    # Mock hashlib to just pass the hash
    mock_hash = 'hash_mock'
    
    # resolve_approval checks if hmac.compare_digest(db_token, hashed_token).
    # so we just pass "hash_mock" since it directly compares
    # wait, resolve_approval does hmac.compare_digest
    JobManager.resolve_approval('test_approval_multiple', 'approved', 'hash_mock', 'fix123', 'cycle123')
    
    # Verify job status changed to WAITING_FOR_DISPATCH
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = 'test_approval_multiple'")
    row = cursor.fetchone()
    assert row[0] == 'WAITING_FOR_DISPATCH'
    
    final_state = json.loads(row[1])
    assert final_state["awaiting_approval"] is False
    assert final_state["approval_decision"] == "approved"
    assert "approval_payload" not in final_state or final_state["approval_payload"] is None
    
    # Verify history
    assert "resolved_approvals" in final_state
    assert len(final_state["resolved_approvals"]) == 1
    assert final_state["resolved_approvals"][0]["payload"]["fix_id"] == "fix123"
    
    conn.close()

