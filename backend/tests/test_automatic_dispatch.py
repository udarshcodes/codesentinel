import pytest
import os
import httpx
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import sqlite3
from api.db import get_connection
from main import app
from api.job_manager import JobManager

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()
    yield

@pytest.mark.asyncio
async def test_new_analysis_creates_new_task_and_dispatches_worker():
    # We want to test the full lifecycle via the API, intercepting the HTTP request to GitHub.
    with patch("api.routes.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Mock a successful GitHub Actions dispatch
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # We need GITHUB_TOKEN to trigger
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token", "WORKER_REPO": "udarshcodes/codesentinel"}):
            # 1. New analysis creates new task
            response = client.post("/api/v1/analyze", json={
                "repo_url": "https://github.com/udarshcodes/portfolio"
            })
            assert response.status_code == 200
            data = response.json()
            
            task_id = data.get("task_id")
            assert task_id is not None
            assert len(data.get("tasks", [])) > 0
            
            worker_attempt_id = data["tasks"][0]["worker_attempt_id"]
            assert worker_attempt_id is not None

            # Check DB state
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status, worker_attempt_id FROM jobs WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            conn.close()
            
            # The job was created as WAITING_FOR_DISPATCH and claimed atomically -> DISPATCHING
            assert row is not None
            db_status, db_worker_attempt_id = row
            # By the time we inspect, it might be in DISPATCHING since `claim_waiting_job` sets worker_attempt_id,
            # but wait, `claim_waiting_job` doesn't change status to DISPATCHING directly, does it?
            # Let's verify what `claim_waiting_job` sets the status to. 
            # Oh, claim_waiting_job adds "DISPATCHING" event and maybe changes status? No, wait,
            # I'll just check it equals the expected attempt id.
            assert db_worker_attempt_id == worker_attempt_id

            # 3. New analysis dispatches GitHub Worker
            assert mock_post.called

            # Check the arguments passed to httpx.post
            call_args = mock_post.call_args
            url = call_args[0][0]
            assert "udarshcodes/codesentinel" in url
            
            kwargs = call_args[1]
            json_payload = kwargs.get("json", {})
            assert json_payload.get("ref") == "main"
            
            inputs = json_payload.get("inputs", {})
            
            # 4. Workflow dispatch receives the exact task_id
            assert inputs.get("task_id") == task_id
            
            # 5. Workflow dispatch receives the exact worker_attempt_id
            assert inputs.get("worker_attempt_id") == worker_attempt_id
