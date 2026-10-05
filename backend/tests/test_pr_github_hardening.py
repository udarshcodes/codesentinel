import pytest
import os
import subprocess
from unittest.mock import patch, MagicMock

from tools.github_client import (
    create_trusted_pr_workspace,
    check_token_permissions,
    commit_and_push,
    open_pull_request,
    verify_trusted_workspace,
    register_trusted_workspace
)
import tools.github_client

@pytest.fixture
def mock_get_safe_env():
    def _mock_env(*args, **kwargs):
        return {"FAKE": "ENV"}
    with patch("tools.subprocess_runner.get_safe_env", side_effect=_mock_env) as m:
        yield m

def test_check_token_permissions():
    # Test valid permissions
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        
        # Should not raise
        check_token_permissions("https://github.com/foo/bar", "TOKEN")
        
    # Test invalid permissions
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        
        with pytest.raises(RuntimeError, match="GitHub token does not have sufficient permission to create a pull request in the target repository."):
            check_token_permissions("https://github.com/foo/bar", "TOKEN")

def test_commit_and_push_failure_sanitizes_token(tmp_path):
    repo_dir = str(tmp_path)
    # create marker
    with open(os.path.join(repo_dir, ".codesentinel_trusted_workspace"), "w") as f:
        f.write("token")
        
    # Add a file to commit
    with open(os.path.join(repo_dir, "file.txt"), "w") as f:
        f.write("content")
        
    def mock_subprocess_run(args, **kwargs):
        if "diff" in args:
            return MagicMock(returncode=1) # has changes
        if "push" in args:
            raise subprocess.CalledProcessError(1, "git", stderr="fatal: auth failed for SECRET_TOKEN_123")
        return MagicMock(returncode=0)
        
    with patch("subprocess.run", side_effect=mock_subprocess_run):
        with patch("tools.github_client.verify_trusted_workspace", return_value=True):
            with pytest.raises(RuntimeError) as exc:
                commit_and_push(repo_dir, "branch", "msg", "https://github.com/a/b", "SECRET_TOKEN_123", ["file.txt"])
            
            assert "SECRET_TOKEN_123" not in str(exc.value)
            assert "***" in str(exc.value)

def test_open_pull_request_failure_sanitizes_token():
    with patch("tools.github_client.Github") as mock_g:
        mock_repo = MagicMock()
        mock_repo.create_pull.side_effect = Exception("Failed due to SECRET_TOKEN_456 invalid")
        mock_g.return_value.get_repo.return_value = mock_repo
        
        with pytest.raises(RuntimeError) as exc:
            open_pull_request("foo/bar", "branch", "title", "body", "SECRET_TOKEN_456", True, "user")
            
        assert "SECRET_TOKEN_456" not in str(exc.value)
        assert "***" in str(exc.value)

def test_trusted_workspace_validation():
    with patch("tools.github_client._trusted_workspaces", {}):
        assert verify_trusted_workspace("/non/existent", "fake") == False

def test_create_trusted_pr_workspace_public_fallback(mock_get_safe_env):
    def mock_run(args, **kwargs):
        if "clone" in args and "GIT_CONFIG_COUNT" in kwargs.get("env", {}):
            raise subprocess.CalledProcessError(1, "git", stderr="Authentication failed")
        return MagicMock(returncode=0, stdout="")
        
    def mock_requests_get(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"private": False})
        return mock_resp
        
    with patch("subprocess.run", side_effect=mock_run) as run_mock:
        with patch("requests.get", side_effect=mock_requests_get) as req_mock:
            with patch("tools.github_client.register_trusted_workspace", return_value="token"):
                res = create_trusted_pr_workspace("https://github.com/foo/public-repo", "SECRET_TOKEN_789")
                
                # Should have fallen back
                assert req_mock.called
                assert run_mock.call_count >= 3 # first clone fails, second clone succeeds, hook config, checkout
                
def test_create_trusted_pr_workspace_private_no_fallback(mock_get_safe_env):
    def mock_run(args, **kwargs):
        if "clone" in args and "GIT_CONFIG_COUNT" in kwargs.get("env", {}):
            raise subprocess.CalledProcessError(1, "git", stderr="Authentication failed with SECRET_TOKEN_999")
        return MagicMock(returncode=0, stdout="")
        
    def mock_requests_get(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 404 # private repos return 404 when unauthorized
        return mock_resp
        
    with patch("subprocess.run", side_effect=mock_run) as run_mock:
        with patch("requests.get", side_effect=mock_requests_get):
            with pytest.raises(RuntimeError) as exc:
                create_trusted_pr_workspace("https://github.com/foo/private-repo", "SECRET_TOKEN_999")
                
            assert "SECRET_TOKEN_999" not in str(exc.value)
            assert "***" in str(exc.value)
