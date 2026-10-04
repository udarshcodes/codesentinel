import os
import sys
import pytest
import shutil
import tempfile
import asyncio
import subprocess

from tools.github_client import commit_and_push, create_trusted_pr_workspace
from worker import run_worker
from models.pipeline_state import PipelineState
from unittest.mock import patch, MagicMock

def test_untrusted_workspace_cannot_commit():
    """Test B: Attempting trusted Git operations from an untrusted workspace fails."""
    temp_dir = tempfile.mkdtemp(prefix="untrusted_")
    try:
        with pytest.raises(ValueError, match="Security Violation: Attempted to run trusted git operations on untrusted workspace"):
            commit_and_push(
                local_path=temp_dir,
                branch_name="test",
                message="test",
                push_repo_url="dummy",
                token="dummy",
                files=["test.py"]
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_trusted_workspace_creation():
    """Test A: PR creation succeeds through the legitimate trusted workspace flow."""
    # create_trusted_pr_workspace should create the marker
    temp_dir = tempfile.mkdtemp(prefix="dummy_")
    try:
        # Mock subprocess to avoid real git clone
        with patch("subprocess.run") as mock_run:
            workspace = create_trusted_pr_workspace("https://github.com/dummy/repo", "dummy_token", "dummy_sha")
            assert os.path.exists(os.path.join(workspace, ".codesentinel_trusted_workspace"))
            shutil.rmtree(workspace, ignore_errors=True)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.mark.skipif(os.name == 'nt', reason="Shell script execution test requires Linux")
def test_sandbox_tool_verification_missing_tool():
    """Test 10: Sandbox tool verification fails when a required executable is absent."""
    # Run the script with a minimal PATH that contains bash but not node/java
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sandbox/scripts/verify-tools.sh"))
    env = os.environ.copy()
    env["PATH"] = "/bin:/usr/bin"
    result = subprocess.run([script_path], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "FATAL: Required tool" in result.stdout or "FATAL: Required tool" in result.stderr

def test_forged_trusted_marker_cannot_bypass_trust():
    """Test C: Forging the marker inside an untrusted workspace does not bypass the intended security boundary."""
    # We verify that pr_author creates its own trusted workspace and doesn't reuse the untrusted one
    from agents.pr_author import agent_pr_author
    
    state = {
        "repo_local_path": "/tmp/untrusted",
        "repo_url": "https://github.com/dummy/repo",
        "patches": [{"applied": True, "file": "test.py", "patch": "diff"}],
        "validation_results": [{"passed": True}],
        "security_verified": True
    }
    
    with patch.dict(os.environ, {"GITHUB_TOKEN": "dummy"}):
        from agents.pr_author import agent_pr_author
        with patch("os.path.exists", return_value=True), \
             patch("tools.github_client.create_trusted_pr_workspace", return_value="/tmp/trusted_workspace") as mock_create_workspace, \
             patch("tools.github_client.prepare_repo_for_push", return_value={"branch_name": "b", "push_repo_url": "url", "repo_name": "r", "user_login": "u", "is_owner": True}), \
             patch("agents.pr_author.run_isolated_subprocess", return_value={"status": "SUCCESS", "stdout": "test.py\n"}), \
             patch("tools.github_client.commit_and_push", return_value=True) as mock_commit_and_push, \
             patch("tools.github_client.open_pull_request", return_value="http://pr"), \
             patch("agents.pr_author.GROQ_API_KEYS", ["dummy"]), \
             patch("agents.pr_author.invoke_llm", return_value={"title": "t", "description": "d"}), \
             patch("shutil.copy2"), \
             patch("shutil.rmtree"), \
             patch("os.makedirs"):
             
            # Simulate .codesentinel_trusted_workspace exists in untrusted path
            result = asyncio.run(agent_pr_author(state))
            
            mock_create_workspace.assert_called_once()
            # commit_and_push should be called with the newly created trusted workspace, NOT the forged untrusted one
            mock_commit_and_push.assert_called_once()
            assert mock_commit_and_push.call_args[1]["local_path"] == "/tmp/trusted_workspace"

@patch("worker.authenticated_post")
@patch("worker.authenticated_get")
@patch("tools.sandbox_runner.check_sandbox_capabilities")
def test_worker_resumes_on_fresh_filesystem(mock_check, mock_get, mock_post):
    """Test 5 & 6 & 7 & 8: Worker reconstructs repository from repo_url and commit_sha if repo_local_path is missing."""
    import worker
    
    stale_path = "/tmp/does_not_exist_xyz123"
    assert not os.path.exists(stale_path)

    existing_state = {
        "repo_url": "https://github.com/dummy/repo",
        "commit_sha": "abc1234",
        "repo_local_path": stale_path,
        "patches": [{"applied": True, "patch": "dummy_patch", "file": "dummy.py"}]
    }

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json = MagicMock(return_value={"pipeline_state": existing_state})
    mock_get.return_value = mock_res
    
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post.return_value = mock_post_res

    env_vars = {
        "TASK_ID": "t1",
        "REPO_URL": "https://github.com/dummy/repo",
        "BACKEND_URL": "http://backend",
        "WORKER_ATTEMPT_ID": "w1",
        "WORKER_WEBHOOK_SECRET": "secret",
        "ENVIRONMENT": "production"
    }

    with patch.dict(os.environ, env_vars), \
         patch("subprocess.run") as mock_run, \
         patch("tools.patch_applier.apply_patch", return_value={"success": True}) as mock_apply, \
         patch("worker.langgraph_app.astream") as mock_astream, \
         patch("worker.TASK_ID", "t1"), \
         patch("worker.REPO_URL", "https://github.com/dummy/repo"), \
         patch("worker.BACKEND_URL", "http://backend"), \
         patch("worker.WORKER_ATTEMPT_ID", "w1"), \
         patch("worker.WORKER_SECRET", "secret"):
        
        # Stop worker after first node
        async def mock_iter():
            yield {"repo_mapper": {"repo_local_path": "dummy"}}
            
        mock_astream.return_value = mock_iter()

        asyncio.run(worker.run_worker())

        # Check if git clone was called
        clone_calls = [c for c in mock_run.call_args_list if len(c.args) > 0 and "clone" in c.args[0]]
        assert len(clone_calls) > 0
        
        # Check if apply_patch was called
        mock_apply.assert_called_once_with("dummy_patch", clone_calls[0].args[0][6], "dummy.py")
