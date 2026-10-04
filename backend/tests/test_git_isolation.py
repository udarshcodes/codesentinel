import os
import json
import tempfile
import subprocess
import pytest
from unittest.mock import patch
from tools.subprocess_runner import get_safe_env

def test_a_clone_env_may_contain_token():
    os.environ["GITHUB_TOKEN"] = "super_secret_clone_token"
    env = get_safe_env(keep_github_token=True)
    assert "GITHUB_TOKEN" in env
    assert env["GITHUB_TOKEN"] == "super_secret_clone_token"
    assert env.get("GIT_TERMINAL_PROMPT") == "0"

def test_b_checkout_safe_env_must_not_contain_token():
    os.environ["GITHUB_TOKEN"] = "super_secret_clone_token"
    os.environ["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: bearer super_secret_clone_token"
    os.environ["GIT_CONFIG_KEY_0"] = "http.extraHeader"
    os.environ["GIT_CONFIG_COUNT"] = "1"
    os.environ["HOME"] = "/home/test"
    os.environ["USERPROFILE"] = "C:\\Users\\test"
    
    env = get_safe_env(keep_github_token=False)
    
    assert "GITHUB_TOKEN" not in env
    assert "GIT_CONFIG_VALUE_0" not in env
    assert "GIT_CONFIG_KEY_0" not in env
    assert "GIT_CONFIG_COUNT" not in env
    assert "HOME" not in env
    assert "USERPROFILE" not in env
    assert env.get("GIT_TERMINAL_PROMPT") == "0"

def test_c_safe_env_removes_other_secrets():
    os.environ["GROQ_API_KEY"] = "groq_secret"
    os.environ["GROQ_API_KEY_1"] = "groq_secret_1"
    os.environ["WORKER_WEBHOOK_SECRET"] = "webhook_secret"
    os.environ["ADMIN_SECRET"] = "admin_secret"
    
    env = get_safe_env(keep_github_token=False)
    
    assert "GROQ_API_KEY" not in env
    assert "GROQ_API_KEY_1" not in env
    assert "WORKER_WEBHOOK_SECRET" not in env
    assert "ADMIN_SECRET" not in env

@pytest.mark.asyncio
async def test_d_clone_uses_no_checkout():
    from agents.repo_mapper import agent_repo_mapper
    state = {"repo_url": "https://github.com/owner/repo"}
    
    with patch("subprocess.run") as mock_run:
        with patch("tools.auth.is_lease_lost", return_value=False):
            class DummyProcess:
                stdout = "file1.py\nfile2.py"
                stderr = ""
                returncode = 0
            
            mock_run.return_value = DummyProcess()
            
            res = await agent_repo_mapper(state)
            
            # Verify the first call to subprocess.run is git clone --no-checkout
            clone_call = mock_run.call_args_list[0]
            cmd = clone_call[0][0]
            assert cmd[0] == "git"
            assert cmd[1] == "clone"
            assert cmd[2] == "--no-checkout"

def test_e_malicious_checkout_cannot_see_secrets():
    # Construct a controlled test repository that executes a harmless command during checkout
    temp_dir = tempfile.mkdtemp()
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_dir, check=True)
    
    with open(os.path.join(temp_dir, "test.txt"), "w") as f:
        f.write("hello")
    subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True)
    
    # Create the post-checkout hook to dump environment
    hook_dir = os.path.join(temp_dir, ".git", "hooks")
    os.makedirs(hook_dir, exist_ok=True)
    hook_path = os.path.join(hook_dir, "post-checkout")
    
    import sys
    with open(hook_path, "w") as f:
        f.write(f"#!{sys.executable}\nimport os, json\nwith open('env_dump.json', 'w') as out:\n  json.dump(dict(os.environ), out)\n")
    os.chmod(hook_path, 0o755)

    subprocess.run(["git", "branch", "test-branch"], cwd=temp_dir, check=True)
    
    # Inject fake secrets into the test's process environment
    os.environ["GITHUB_TOKEN"] = "super_secret_gh"
    os.environ["GROQ_API_KEY_1"] = "super_secret_groq"
    os.environ["WORKER_WEBHOOK_SECRET"] = "super_secret_webhook"
    
    safe_env = get_safe_env(keep_github_token=False)
    
    # Trigger checkout with the safe_env (which strips the above secrets)
    # The hook should run and write env_dump.json
    subprocess.run(["git", "checkout", "test-branch"], cwd=temp_dir, env=safe_env, check=True, capture_output=True)
    
    dump_path = os.path.join(temp_dir, "env_dump.json")
    assert os.path.exists(dump_path), "Hook did not run"
    
    with open(dump_path, "r") as f:
        dumped_env = json.load(f)
        
    assert "GITHUB_TOKEN" not in dumped_env
    assert "GROQ_API_KEY_1" not in dumped_env
    assert "WORKER_WEBHOOK_SECRET" not in dumped_env
