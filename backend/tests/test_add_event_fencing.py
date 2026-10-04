import pytest
import sqlite3
from datetime import datetime, timezone
from api.job_manager import JobManager, DB_PATH

def test_add_event_fencing():
    task_id = "test_fencing_123"
    worker_1 = "worker-attempt-1"
    worker_2 = "worker-attempt-2"
    now = datetime.now(timezone.utc).isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    conn.execute(
        "INSERT INTO jobs (task_id, status, worker_attempt_id) VALUES (?, ?, ?)",
        (task_id, "RUNNING", worker_1)
    )
    conn.commit()
    conn.close()
    
    # 1. Missing attempt (external) should fail
    with pytest.raises(TypeError):
        JobManager.add_worker_event(task_id=task_id, status="RUNNING", event_name="pipeline_update", data={}, timestamp=now)
        
    # 2. Missing attempt (internal) should succeed
    JobManager.record_informational_event(task_id=task_id, status="RUNNING", event_name="internal_update", data={}, timestamp=now)
    
    # 3. Wrong attempt should fail (stale worker)
    with pytest.raises(ValueError, match="Stale worker attempt"):
        JobManager.add_worker_event(task_id=task_id, worker_attempt_id="stale-worker", status="RUNNING", event_name="pipeline_update", data={}, timestamp=now)
        
    # 4. Correct attempt should succeed
    JobManager.add_worker_event(task_id=task_id, worker_attempt_id=worker_1, status="RUNNING", event_name="pipeline_update", data={}, timestamp=now)
    
    # Simulate a takeover (worker_2)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET worker_attempt_id = ? WHERE task_id = ?", (worker_2, task_id))
    conn.commit()
    conn.close()
    
    # 5. worker_1 is now stale
    with pytest.raises(ValueError, match="Stale worker attempt"):
        JobManager.add_worker_event(task_id=task_id, worker_attempt_id=worker_1, status="RUNNING", event_name="pipeline_update", data={}, timestamp=now)
        
    # 6. worker_2 is correct
    JobManager.add_worker_event(task_id=task_id, worker_attempt_id=worker_2, status="RUNNING", event_name="pipeline_update", data={}, timestamp=now)
