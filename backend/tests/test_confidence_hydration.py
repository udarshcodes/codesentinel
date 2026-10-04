import pytest
import sqlite3
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from main import app
from api.job_manager import JobManager, DB_PATH

client = TestClient(app)

def test_confidence_hydration_after_refresh():
    task_id = "test_confidence_hydration_123"
    
    # 1. Setup DB state with confidence_score
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    
    import hashlib
    raw_token = "valid_token"
    hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
    pipeline_state = json.dumps({"confidence_score": 95, "status": "COMPLETED"})
    cursor.execute(
        "INSERT INTO jobs (task_id, status, pipeline_state, view_token) VALUES (?, ?, ?, ?)",
        (task_id, "COMPLETED", pipeline_state, hashed_token)
    )
    conn.commit()
    conn.close()

    # 3. Fetch from /view route
    response = client.get(f"/api/v1/job/{task_id}/view", headers={"Authorization": f"Bearer {raw_token}"})
    assert response.status_code == 200
    job = response.json()
    
    # 4. Verify confidence_score is exposed correctly
    state_data = job.get("pipeline_state", {})
    assert state_data.get("confidence_score") == 95
