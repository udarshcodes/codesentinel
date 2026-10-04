import pytest
import sqlite3
import uuid
from datetime import datetime, timezone
from api.job_manager import JobManager, DB_PATH

def setup_test_job(task_id: str):
    JobManager.create_job(task_id, "https://github.com/test/repo", commit_sha="test_commit_sha")

def test_transition_job_state_no_bypass():
    """
    Verifies that transition_job_state explicitly rejects invalid transitions (e.g. RUNNING -> DISPATCHING)
    even if callers attempt to bypass it with the old operation kwargs.
    """
    task_id = "test-no-bypass-" + str(uuid.uuid4())
    setup_test_job(task_id)

    # Set to RUNNING
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'RUNNING' WHERE task_id = ?", (task_id,))
    conn.commit()

    # Attempt transition
    now = datetime.now(timezone.utc).isoformat()
    try:
        # We pass an extra kwargs dict that might simulate an old caller trying to use operation=STALE_WORKER_RECOVERY
        # Python will naturally raise TypeError if the arg is missing, but even if we do it via a wrapper or some other way,
        # we just want to ensure it strictly raises ValueError for invalid state transition
        # Let's test the native function. It shouldn't accept operation kwarg anymore.
        JobManager.transition_job_state(
            cursor, 
            task_id, 
            "DISPATCHING", 
            timestamp=now,
            operation="STALE_WORKER_RECOVERY"  # This should raise TypeError since we removed it
        )
        assert False, "Expected TypeError due to removed operation parameter"
    except TypeError:
        pass  # Good! The bypass parameter is gone.

    # Now verify the normal valid transition enforcement for RUNNING -> DISPATCHING
    with pytest.raises(ValueError) as excinfo:
        JobManager.transition_job_state(
            cursor, 
            task_id, 
            "DISPATCHING", 
            timestamp=now
        )
    assert "Invalid state transition: RUNNING -> DISPATCHING" in str(excinfo.value)
    
    conn.rollback()
    conn.close()
