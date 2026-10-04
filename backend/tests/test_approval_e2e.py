import pytest
import sqlite3
import hashlib
from api.job_manager import JobManager, DB_PATH

@pytest.mark.asyncio
async def test_approval_rejection_flow():
    task_id = "test_app_rej_123"
    token = "secret_token"
    hashed = hashlib.sha256(token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM approval_credentials WHERE task_id = ?", (task_id,))
    
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=1)).isoformat()
    import json
    import uuid
    cycle_id = str(uuid.uuid4())
    initial_state = {"awaiting_approval": True, "approval_state": "pending", "approval_decision": None, "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "pending"}], "approval_cycle_id": cycle_id}
    cursor.execute("INSERT INTO jobs (task_id, status, pipeline_state) VALUES (?, ?, ?)", (task_id, "WAITING_FOR_APPROVAL", json.dumps(initial_state)))
    cursor.execute("INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at) VALUES (?, ?, ?, ?, ?, 'active', ?)", (str(uuid.uuid4()), cycle_id, task_id, "fix1", hashed, expires))
    conn.commit()
    conn.close()

    JobManager.resolve_approval(task_id, "rejected", hashed, "fix1", cycle_id)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, approval_decision FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "NEEDS_REVIEW"
    assert row[1] == "rejected"

@pytest.mark.asyncio
async def test_approval_approved_flow():
    task_id = "test_app_appr_123"
    token = "secret_token"
    hashed = hashlib.sha256(token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM approval_credentials WHERE task_id = ?", (task_id,))
    
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=1)).isoformat()
    
    import json
    import uuid
    cycle_id = str(uuid.uuid4())
    initial_state = {"awaiting_approval": True, "approval_state": "pending", "approval_decision": None, "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "pending"}], "approval_cycle_id": cycle_id}
    cursor.execute("INSERT INTO jobs (task_id, status, pipeline_state) VALUES (?, ?, ?)", (task_id, "WAITING_FOR_APPROVAL", json.dumps(initial_state)))
    cursor.execute("INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at) VALUES (?, ?, ?, ?, ?, 'active', ?)", (str(uuid.uuid4()), cycle_id, task_id, "fix1", hashed, expires))
    conn.commit()
    conn.close()

    JobManager.resolve_approval(task_id, "approved", hashed, "fix1", cycle_id)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, approval_decision, pipeline_state FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "WAITING_FOR_DISPATCH"
    assert row[1] == "approved"
    
    p_state = json.loads(row[2])
    assert p_state["awaiting_approval"] is False
    assert p_state["approval_decision"] == "approved"
