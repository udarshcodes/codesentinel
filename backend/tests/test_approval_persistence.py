import pytest
import sqlite3
import json
import asyncio
from unittest.mock import patch, MagicMock

from api.job_manager import JobManager, DB_PATH
from worker import prepare_next_approval_cycle, run_worker

@pytest.fixture
def clean_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()

@pytest.mark.asyncio
async def test_worker_aborts_on_persistence_failure(clean_db):
    task_id = "test_persistence_1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status) VALUES (?, ?, ?)",
        (task_id, "w1", "RUNNING")
    )
    conn.commit()
    conn.close()
    
    with patch("worker.TASK_ID", task_id), \
         patch("worker.REPO_URL", "http://repo"), \
         patch("worker.BACKEND_URL", "http://backend"), \
         patch("worker.WORKER_ATTEMPT_ID", "w1"), \
         patch("worker.authenticated_get") as mock_get, \
         patch("worker.post_event") as mock_post_event, \
         patch("worker.authenticated_post") as mock_post:
             
        class MockGetRes:
            status_code = 200
            def json(self):
                return {
                    "pipeline_state": {
                        "status": "RUNNING",
                        "awaiting_approval": False,
                        "repair_plan": [{"fix_id": "fix1", "status": "pending", "risk_level": "high-risk"}],
                        "retry_count": 0
                    }
                }
        mock_get.return_value = MockGetRes()
        
        class MockPost:
            def __call__(self, url, data=None):
                class MockResponse:
                    def __init__(self, status_code, text="Error"):
                        self.status_code = status_code
                        self.text = text
                if url.endswith("/heartbeat"):
                    return MockResponse(200)
                return MockResponse(500)
        
        mock_post.side_effect = MockPost()
        
        # Mock langgraph_app.astream to yield repair_planner output
        async def mock_astream(*args, **kwargs):
            yield {"repair_planner": {"some": "data"}}
        
        with patch("worker.langgraph_app.astream", mock_astream):
            # In run_worker, when persistence fails completely, it raises SystemExit(1)
            with pytest.raises(SystemExit) as exit_exc:
                await run_worker()
            
        assert exit_exc.value.code == 1
        
        # Ensure approval_required was NEVER emitted!
        for call in mock_post_event.call_args_list:
            assert call.args[1] != "approval_required"

@pytest.mark.asyncio
async def test_worker_aborts_on_409_conflict(clean_db):
    task_id = "test_persistence_2"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status) VALUES (?, ?, ?)",
        (task_id, "w1", "RUNNING")
    )
    conn.commit()
    conn.close()
    
    with patch("worker.TASK_ID", task_id), \
         patch("worker.REPO_URL", "http://repo"), \
         patch("worker.BACKEND_URL", "http://backend"), \
         patch("worker.WORKER_ATTEMPT_ID", "w1"), \
         patch("worker.authenticated_get") as mock_get, \
         patch("worker.post_event") as mock_post_event, \
         patch("worker.authenticated_post") as mock_post:
             
        class MockGetRes:
            status_code = 200
            def json(self):
                return {
                    "pipeline_state": {
                        "status": "RUNNING",
                        "awaiting_approval": False,
                        "repair_plan": [{"fix_id": "fix1", "status": "pending", "risk_level": "high-risk"}],
                        "retry_count": 0
                    }
                }
        mock_get.return_value = MockGetRes()
        
        class MockPost:
            def __call__(self, url, data=None):
                class MockResponse:
                    def __init__(self, status_code, text="Conflict"):
                        self.status_code = status_code
                        self.text = text
                if url.endswith("/heartbeat"):
                    return MockResponse(200)
                return MockResponse(409)
        
        mock_post.side_effect = MockPost()
        
        async def mock_astream(*args, **kwargs):
            yield {"repair_planner": {"some": "data"}}
            
        with patch("worker.langgraph_app.astream", mock_astream):
            with pytest.raises(SystemExit) as exit_exc:
                await run_worker()
            
        assert exit_exc.value.code == 153
        
        for call in mock_post_event.call_args_list:
            assert call.args[1] != "approval_required"

@pytest.mark.asyncio
async def test_worker_emits_event_on_success(clean_db):
    task_id = "test_persistence_3"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status) VALUES (?, ?, ?)",
        (task_id, "w1", "RUNNING")
    )
    conn.commit()
    conn.close()
    
    with patch("worker.TASK_ID", task_id), \
         patch("worker.REPO_URL", "http://repo"), \
         patch("worker.BACKEND_URL", "http://backend"), \
         patch("worker.WORKER_ATTEMPT_ID", "w1"), \
         patch("worker.authenticated_get") as mock_get, \
         patch("worker.post_event") as mock_post_event, \
         patch("worker.authenticated_post") as mock_post, \
         patch("worker.asyncio.sleep"): # Skip sleep in loop
             
        class MockGetRes:
            status_code = 200
            def json(self):
                return {
                    "pipeline_state": {
                        "status": "RUNNING",
                        "awaiting_approval": False,
                        "repair_plan": [{"fix_id": "fix1", "status": "pending", "risk_level": "high-risk"}],
                        "retry_count": 0
                    }
                }
        mock_get.return_value = MockGetRes()
        
        class MockPost:
            def __init__(self):
                self.approval_calls = 0
            def __call__(self, url, data=None):
                class MockResponse:
                    def __init__(self, status_code, text="OK"):
                        self.status_code = status_code
                        self.text = text
                if url.endswith("/heartbeat"):
                    return MockResponse(200)
                if url.endswith("/state") and data and data.get("status") == "WAITING_FOR_APPROVAL":
                    self.approval_calls += 1
                    if self.approval_calls == 1:
                        return MockResponse(500)
                    return MockResponse(200)
                return MockResponse(200)
        
        mock_post.side_effect = MockPost()
        
        async def mock_astream(*args, **kwargs):
            yield {"repair_planner": {"some": "data"}}
            
        with patch("worker.langgraph_app.astream", mock_astream):
            # Should not raise SystemExit, should return cleanly
            await run_worker()
        
        # Ensure approval_required WAS emitted
        event_emitted = False
        for call in mock_post_event.call_args_list:
            if call.args[1] == "approval_required":
                event_emitted = True
                assert call.args[0] == "WAITING_FOR_APPROVAL"
        
        assert event_emitted
