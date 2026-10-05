import pytest
import sys
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Add backend to path for tests
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import worker
from tools.llm_router import LLMExhaustionError

@pytest.fixture(autouse=True)
def setup_worker_env():
    # Patch global worker configuration
    with patch.object(worker, "TASK_ID", "test-task"), \
         patch.object(worker, "REPO_URL", "https://github.com/udarshcodes/codesentinel"), \
         patch.object(worker, "COMMIT_SHA", "abcdef"):
        yield

@pytest.fixture
def mock_dependencies():
    with patch("worker.langgraph_app") as mock_app, \
         patch("worker.authenticated_get", new_callable=AsyncMock) as mock_get, \
         patch("worker.authenticated_post", new_callable=AsyncMock) as mock_post, \
         patch("worker.post_event", new_callable=AsyncMock) as mock_post_event, \
         patch("tools.subprocess_runner.clone_github_repo"), \
         patch("subprocess.run"), \
         patch("tempfile.mkdtemp", return_value="/tmp/test"), \
         patch("os.makedirs"):
         
        # Mock successful state fetch returning None (fresh job) by default
        res_mock = MagicMock()
        res_mock.status_code = 200
        res_mock.json.return_value = {"pipeline_state": None}
        mock_get.return_value = res_mock
        
        # Mock successful state persist
        post_res_mock = MagicMock()
        post_res_mock.status_code = 200
        mock_post.return_value = post_res_mock

        yield mock_app, mock_get, mock_post, mock_post_event

@pytest.mark.asyncio
async def test_fresh_worker_state_contains_repo_url(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    # Empty iterator for LangGraph (finishes instantly)
    async def async_gen():
        return
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit") as mock_exit:
        await worker.run_worker()
        
    # Should exit 0 or not exit (which means success)
    # The pipeline should complete and run post_event("COMPLETED")
    mock_post_event.assert_any_call("COMPLETED", "pipeline_complete", {"pr_url": "", "pr_error": "", "confidence_score": 0.0, "validated_fixes": []})
    
    # State should be correctly initialized and passed to langgraph_app.astream
    args, kwargs = mock_app.astream.call_args
    state = args[0]
    assert state["repo_url"] == "https://github.com/udarshcodes/codesentinel"
    assert state["task_id"] == "test-task"

@pytest.mark.asyncio
async def test_resumed_state_containing_repo_url_works(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    res_mock = MagicMock()
    res_mock.status_code = 200
    res_mock.json.return_value = {"pipeline_state": {"repo_url": "https://github.com/custom/repo", "task_id": "test-task", "commit_sha": "12345"}}
    mock_get.return_value = res_mock
    
    async def async_gen():
        return
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit"):
        await worker.run_worker()
        
    args, kwargs = mock_app.astream.call_args
    state = args[0]
    assert state["repo_url"] == "https://github.com/custom/repo"

@pytest.mark.asyncio
async def test_resumed_state_missing_repo_url_is_repaired(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    res_mock = MagicMock()
    res_mock.status_code = 200
    res_mock.json.return_value = {"pipeline_state": {"task_id": "test-task", "commit_sha": "12345"}}
    mock_get.return_value = res_mock
    
    async def async_gen():
        return
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit"):
        await worker.run_worker()
        
    args, kwargs = mock_app.astream.call_args
    state = args[0]
    assert state["repo_url"] == "https://github.com/udarshcodes/codesentinel"

@pytest.mark.asyncio
async def test_resumed_state_missing_task_id_repaired(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    res_mock = MagicMock()
    res_mock.status_code = 200
    res_mock.json.return_value = {"pipeline_state": {"repo_url": "https://github.com/custom/repo", "commit_sha": "12345"}}
    mock_get.return_value = res_mock
    
    async def async_gen():
        return
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit"):
        await worker.run_worker()
        
    args, kwargs = mock_app.astream.call_args
    state = args[0]
    assert state["task_id"] == "test-task"

@pytest.mark.asyncio
async def test_resumed_state_missing_commit_sha_repaired(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    res_mock = MagicMock()
    res_mock.status_code = 200
    res_mock.json.return_value = {"pipeline_state": {"repo_url": "https://github.com/custom/repo", "task_id": "test-task"}}
    mock_get.return_value = res_mock
    
    async def async_gen():
        return
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit"):
        await worker.run_worker()
        
    args, kwargs = mock_app.astream.call_args
    state = args[0]
    assert state["commit_sha"] == "abcdef"

@pytest.mark.asyncio
async def test_missing_repo_url_after_fallback_fatal_error(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    res_mock = MagicMock()
    res_mock.status_code = 200
    res_mock.json.return_value = {"pipeline_state": {"task_id": "test-task"}}
    mock_get.return_value = res_mock
    
    with patch.object(worker, "REPO_URL", ""), patch("sys.exit", side_effect=SystemExit) as mock_exit, patch("worker.validate_env"):
        try:
            await worker.run_worker()
        except SystemExit:
            pass
        
    mock_post_event.assert_any_call("FAILED", "pipeline_error", {"error": "CRITICAL: Missing repo_url in resumed state, and REPO_URL fallback was empty."})
    mock_exit.assert_called_with(1)

@pytest.mark.asyncio
async def test_langgraph_keyerror_failures_cause_nonzero_exit(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    async def async_gen():
        raise KeyError("repo_url")
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit") as mock_exit:
        await worker.run_worker()
        
    mock_exit.assert_called_with(1)
    mock_post_event.assert_any_call("FAILED", "pipeline_error", {"error": "'repo_url'"})

@pytest.mark.asyncio
async def test_failed_events_sent_before_termination(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    async def async_gen():
        raise RuntimeError("Something went wrong")
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit") as mock_exit:
        await worker.run_worker()
        
    mock_post_event.assert_any_call("FAILED", "pipeline_error", {"error": "Something went wrong"})
    mock_exit.assert_called_with(1)

@pytest.mark.asyncio
async def test_successful_pipelines_exit_zero(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    async def async_gen():
        return
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit") as mock_exit:
        await worker.run_worker()
        
    mock_exit.assert_not_called()
    mock_post_event.assert_any_call("COMPLETED", "pipeline_complete", {"pr_url": "", "pr_error": "", "confidence_score": 0.0, "validated_fixes": []})

@pytest.mark.asyncio
async def test_waiting_for_approval_not_failure(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    async def async_gen():
        yield {"repair_planner": {"repair_plan": [{"risk_level": "high-risk", "status": "pending", "fix_id": "fix_1"}]}}
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit") as mock_exit:
        await worker.run_worker()
        
    mock_exit.assert_not_called()
    call_args_list = mock_post_event.call_args_list
    assert any(call[0][0] == "WAITING_FOR_APPROVAL" for call in call_args_list)

@pytest.mark.asyncio
async def test_waiting_for_llm_capacity_not_failure(mock_dependencies):
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    async def async_gen():
        raise LLMExhaustionError("Exhausted", last_error="Exhausted", reset_time=300, model="llama")
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch("sys.exit") as mock_exit:
        await worker.run_worker()
        
    mock_exit.assert_called_with(0)

@pytest.mark.asyncio
async def test_ssrf_validation_intact(mock_dependencies):
    # This is handled upstream or in the clone validation, but we can just test that worker doesn't overwrite
    # a perfectly valid state with an injected malicious REPO_URL.
    mock_app, mock_get, mock_post, mock_post_event = mock_dependencies
    
    res_mock = MagicMock()
    res_mock.status_code = 200
    res_mock.json.return_value = {"pipeline_state": {"repo_url": "https://github.com/safe/repo", "task_id": "test-task", "commit_sha": "12345"}}
    mock_get.return_value = res_mock
    
    async def async_gen():
        return
        yield
    mock_app.astream.return_value = async_gen()
    
    with patch.object(worker, "REPO_URL", "file:///etc/passwd"), patch("sys.exit") as mock_exit:
        await worker.run_worker()
        
    args, kwargs = mock_app.astream.call_args
    state = args[0]
    # Ensure the safe repo_url from the DB wasn't overwritten by the potentially malicious injected one
    assert state["repo_url"] == "https://github.com/safe/repo"
