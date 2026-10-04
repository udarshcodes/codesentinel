import asyncio
import sqlite3
import pytest
import os
import json
import uuid
from datetime import datetime, timezone, timedelta

from api.job_manager import JobManager, DB_PATH

@pytest.fixture(autouse=True)
def setup_teardown():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM approval_credentials")
    cursor.execute("DELETE FROM job_events")
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM approval_credentials")
    cursor.execute("DELETE FROM job_events")
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_concurrent_claim_waiting_job():
    """Verify two scheduler processes cannot reclaim the same task simultaneously."""
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    stale_time = (now - timedelta(minutes=10)).isoformat()
    
    # Insert a stale RUNNING job
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, updated_at, worker_heartbeat_at, worker_attempt_id) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "https://github.com/foo/bar", "RUNNING", stale_time, stale_time, "old-attempt-123")
    )
    conn.commit()
    conn.close()

    # Try to claim concurrently
    async def try_claim():
        # run in executor since recover_stale_worker_claim is blocking
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, JobManager.recover_stale_worker_claim, task_id)

    results = await asyncio.gather(
        try_claim(),
        try_claim(),
        try_claim(),
        try_claim(),
        try_claim(),
    )

    # Only one of these should have successfully claimed the job and returned an attempt ID.
    # The others should return None.
    successes = [r for r in results if r is not None]
    
    assert len(successes) == 1, f"Expected exactly 1 successful claim, got {len(successes)}"

@pytest.mark.asyncio
async def test_concurrent_approval():
    """Verify concurrent approval submissions don't lead to race conditions."""
    import hashlib
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    approval_token = "secret-token"
    hashed_token = hashlib.sha256(approval_token.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    import json
    initial_state = {"awaiting_approval": True, "approval_state": "pending", "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "pending"}], "approval_cycle_id": "cycle1"}
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, updated_at, pipeline_state) VALUES (?, ?, ?, ?, ?)",
        (task_id, "https://github.com/foo/bar", "WAITING_FOR_APPROVAL", now, json.dumps(initial_state))
    )
    cursor.execute(
        "INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at) VALUES (?, ?, ?, ?, ?, 'active', ?)",
        (str(uuid.uuid4()), "cycle1", task_id, "fix1", hashed_token, expires)
    )
    conn.commit()
    conn.close()

    async def try_approve():
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, JobManager.resolve_approval, task_id, "approved", hashed_token, "fix1", "cycle1")
        except Exception as e:
            return e

    results = await asyncio.gather(
        try_approve(),
        try_approve(),
        try_approve()
    )
    
    successes = [r for r in results if isinstance(r, dict) and r.get("status") in ("WAITING_FOR_DISPATCH", "NEEDS_REVIEW")]
    errors = [r for r in results if isinstance(r, Exception)]
    
    assert len(successes) == 1, f"Expected exactly 1 successful approval, got {len(successes)}. Results: {results}"
    assert len(errors) == 2, f"Expected exactly 2 approval failures, got {len(errors)}"
    assert "Approval already resolved" in str(errors[0]) or "Task is not in a state that can be approved" in str(errors[0])
