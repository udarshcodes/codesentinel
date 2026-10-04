import pytest
from fastapi.testclient import TestClient
import sqlite3
import json
import uuid
import datetime

from main import app
from api.job_manager import JobManager, DB_PATH

client = TestClient(app)

def test_agent_hydration_key():
    task_id = str(uuid.uuid4())
    repo_url = "https://github.com/test/repo"
    
    # 1. Create a job
    JobManager.create_job(task_id, repo_url, view_token="dummy_view", commit_sha="sha123")
    
    # We must set a worker attempt so we can add worker events
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET worker_attempt_id = 'local', status = 'RUNNING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    # 2. Add some agent_complete events
    JobManager.add_worker_event(
        task_id=task_id,
        worker_attempt_id="local",
        status="RUNNING",
        event_name="agent_complete",
        data={"agent": "static_analysis", "findings": ["1"]},
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    
    # 3. Check get_events format
    events = JobManager.get_events(task_id)
    assert len(events) > 0
    assert "event" in events[0]
    assert events[0]["event"] == "agent_complete"
    assert "agent" in events[0]["data"]
    
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM job_events WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
