import pytest
from datetime import datetime, timezone
import uuid
from fastapi.testclient import TestClient
from api.job_manager import JobManager
from tools.llm_router import LLMExhaustionError
from agents.repo_mapper import agent_repo_mapper
from config import GROQ_API_KEYS
from api.db import get_connection
from main import app

@pytest.fixture
def clean_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM jobs")
    conn.commit()
    return conn

@pytest.fixture
def client():
    return TestClient(app)

def test_new_analysis_creates_new_task(client, clean_db, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")
    
    class MockResponse:
        status_code = 201
        text = ""
        
    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def post(self, *args, **kwargs):
            return MockResponse()
            
    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    res = client.post("/api/v1/analyze", json={"repo_url": "https://github.com/foo/bar"})
    assert res.status_code == 200
    data = res.json()
    assert "tasks" in data
    assert len(data["tasks"]) == 1
    task = data["tasks"][0]
    
    # 1. New analysis creates a new task
    task_id = task["task_id"]
    assert task_id is not None
    
    # 2. New analysis creates a new worker attempt
    job = JobManager.get_job(task_id)
    assert job["worker_attempt_id"] is not None
    assert job["status"] == "DISPATCHING"

def test_already_completed_task_cannot_rerun(clean_db):
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    cursor = clean_db.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, repo_url, worker_attempt_id, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "COMPLETED", "https://github.com/foo/bar", "attempt-1", now, now)
    )
    clean_db.commit()
    
    # Test that JobManager won't allow state transition if already completed (unless specific override)
    with pytest.raises(ValueError, match="Invalid state transition"):
        JobManager.transition_job_state(cursor, task_id, "RUNNING", worker_attempt_id="attempt-1")
    
@pytest.mark.asyncio
@pytest.mark.parametrize('response', [[], {'error': 'invalid JSON'}, ValueError('invalid JSON')])
async def test_repo_mapper_json_validate_fallback(tmp_path, monkeypatch, response):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    monkeypatch.setenv('TEMP_REPO_PATH', str(tmp_path))
    monkeypatch.setattr('tools.subprocess_runner.clone_github_repo', lambda *args: None)
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: SimpleNamespace(stdout=''))
    monkeypatch.setattr('agents.repo_mapper.GROQ_API_KEYS', ['test'])
    llm = AsyncMock(side_effect=response) if isinstance(response, Exception) else AsyncMock(return_value=response)
    monkeypatch.setattr('agents.repo_mapper.invoke_llm', llm)
    monkeypatch.setattr('tools.vector_store.index_codebase', lambda *args: {'status': 'unavailable'})
    result = await agent_repo_mapper({'repo_url': 'https://github.com/foo/bar', 'commit_sha': 'abc'})
    assert result['repo_local_path']
    assert result['knowledge_graph']['language'] == 'unknown'
    assert result['knowledge_graph']['test_framework'] == ''
    assert result['knowledge_graph']['modules'] == []

@pytest.mark.asyncio
async def test_repo_mapper_llm_exhaustion_propagation(monkeypatch):
    # Mock clone_github_repo so it doesn't fail
    def mock_clone(*args, **kwargs):
        pass
    monkeypatch.setattr("tools.subprocess_runner.clone_github_repo", mock_clone)
    class MockProcess:
        stdout = ""
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockProcess())
    
    # Mock invoke_llm to raise LLMExhaustionError
    async def mock_invoke_llm(*args, **kwargs):
        raise LLMExhaustionError("WAITING_FOR_LLM_CAPACITY", "test", 300, "test")
    monkeypatch.setattr("agents.repo_mapper.invoke_llm", mock_invoke_llm)
    
    # Enable GROQ_API_KEYS to reach the llm block
    GROQ_API_KEYS.append("test")
    
    state = {"repo_url": "https://github.com/foo/bar", "commit_sha": "abc"}
    
    with pytest.raises(LLMExhaustionError):
        await agent_repo_mapper(state)
        
    GROQ_API_KEYS.clear()

