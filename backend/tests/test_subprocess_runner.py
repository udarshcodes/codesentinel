import pytest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from tools.subprocess_runner import run_isolated_subprocess

def test_run_isolated_subprocess_success():
    result = run_isolated_subprocess([sys.executable, "-c", "print('hello world')"], cwd=os.getcwd())
    assert result["status"] == "SUCCESS"
    assert "hello world" in result["stdout"]

def test_run_isolated_subprocess_timeout():
    result = run_isolated_subprocess([sys.executable, "-c", "import time; time.sleep(5)"], cwd=os.getcwd(), timeout=1)
    assert result["status"] == "TIMEOUT"
    assert "Command timed out" in result["error"]

def test_run_isolated_subprocess_malicious_env_leak():
    # Set a secret in the environment
    os.environ["SUPER_SECRET_TOKEN"] = "12345"
    
    # Try to print the environment from the subprocess
    result = run_isolated_subprocess([sys.executable, "-c", "import os; print(os.environ.get('SUPER_SECRET_TOKEN', 'not_found'))"], cwd=os.getcwd())
    
    # The subprocess should NOT have access to SUPER_SECRET_TOKEN
    assert "not_found" in result["stdout"]
    assert "12345" not in result["stdout"]

def test_run_isolated_subprocess_resource_limits():
    if os.name == 'nt':
        pytest.skip("Resource limits via rlimit not supported on Windows")
        
    # Attempt to allocate excessive memory
    script = "a = 'x' * (256 * 1024 * 1024)" # Try to allocate 256MB
    
    # Run with a max_memory of 64MB
    result = run_isolated_subprocess([sys.executable, "-c", script], cwd=os.getcwd(), max_memory_mb=64)
    
    # Should crash with MemoryError or be killed
    assert result["status"] == "FAILED"

from unittest.mock import patch, call
from tools.subprocess_runner import clone_github_repo

@patch("subprocess.run")
def test_clone_github_repo_public_no_token(mock_run):
    clone_github_repo("https://github.com/public/repo", "/tmp/dir", "")
    # Should just do unauthenticated clone
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == ["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-checkout", "https://github.com/public/repo", "/tmp/dir"]
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "GIT_CONFIG_KEY_0" not in kwargs["env"]

@patch("subprocess.run")
def test_clone_github_repo_private_with_token(mock_run):
    clone_github_repo("https://github.com/private/repo", "/tmp/dir", "ghp_SECRET")
    # Should do authenticated clone
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert kwargs["env"]["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert "AUTHORIZATION: bearer ghp_SECRET" in kwargs["env"]["GIT_CONFIG_VALUE_0"]

@patch("subprocess.run")
def test_clone_github_repo_auth_fallback_public(mock_run):
    import subprocess
    # First call (auth) fails (e.g. token lacks access), second call (unauth) succeeds (repo is public)
    mock_run.side_effect = [
        subprocess.CalledProcessError(128, ["git"], stderr="Auth failed"),
        None
    ]
    clone_github_repo("https://github.com/public/repo", "/tmp/dir", "ghp_SECRET")
    assert mock_run.call_count == 2
    # Verify second call was unauthenticated
    args, kwargs = mock_run.call_args_list[1]
    assert "GIT_CONFIG_KEY_0" not in kwargs["env"]

@patch("subprocess.run")
def test_clone_github_repo_auth_fallback_private(mock_run):
    import subprocess
    # Both fail (token lacks access, repo is private)
    mock_run.side_effect = [
        subprocess.CalledProcessError(128, ["git"], stderr="Auth failed with ghp_SECRET"),
        subprocess.CalledProcessError(128, ["git"], stderr="Repo not found")
    ]
    with pytest.raises(RuntimeError) as exc:
        clone_github_repo("https://github.com/private/repo", "/tmp/dir", "ghp_SECRET")
    
    assert mock_run.call_count == 2
    # Should raise the original auth error, but sanitized!
    assert "Auth failed with ***" in str(exc.value)
    assert "ghp_SECRET" not in str(exc.value)
