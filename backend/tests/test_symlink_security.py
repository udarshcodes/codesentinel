import os
import shutil
import sys
import tempfile
import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")

import stat
from tools.safe_repo import safe_walk, safe_read_text, check_no_symlinks
from agents.static_analysis import agent_static_analysis

@pytest.fixture
def test_env():
    temp_base = tempfile.mkdtemp(prefix="symlink_test_")
    
    repo_dir = os.path.join(temp_base, "repo")
    os.makedirs(repo_dir)
    
    host_secret_dir = os.path.join(temp_base, "host")
    os.makedirs(host_secret_dir)
    
    canary_file = os.path.join(host_secret_dir, "canary.txt")
    with open(canary_file, "w") as f:
        f.write("SUPER_SECRET_HOST_DATA")
        
    yield {
        "base": temp_base,
        "repo": repo_dir,
        "host": host_secret_dir,
        "canary": canary_file
    }
    
    shutil.rmtree(temp_base, ignore_errors=True)

def test_direct_symlink(test_env):
    repo = test_env["repo"]
    canary = test_env["canary"]
    
    # Create symlink: repo/outside_secret.txt -> canary
    symlink_path = os.path.join(repo, "outside_secret.txt")
    os.symlink(canary, symlink_path)
    
    # Also create a normal file
    normal_path = os.path.join(repo, "normal.py")
    with open(normal_path, "w") as f:
        f.write("print('safe')")
        
    files_found = []
    symlinks_found = []
    for root, dirs, files, syms in safe_walk(repo):
        for f in files:
            files_found.append(f)
        for s in syms:
            symlinks_found.append(s)
            
    assert "normal.py" in files_found
    assert "outside_secret.txt" not in files_found
    
    sym_bases = [os.path.basename(s) for s in symlinks_found]
    assert "outside_secret.txt" in sym_bases
    
    with pytest.raises(ValueError, match="Symlinks are not allowed"):
        safe_read_text(repo, symlink_path)

def test_directory_symlink(test_env):
    repo = test_env["repo"]
    host_dir = test_env["host"]
    canary = test_env["canary"]
    
    symlink_dir = os.path.join(repo, "external")
    os.symlink(host_dir, symlink_dir)
    
    files_found = []
    for root, dirs, files, syms in safe_walk(repo):
        for f in files:
            files_found.append(os.path.join(root, f))
            
    # Canary should NOT be traversed
    assert len(files_found) == 0

def test_relative_symlink(test_env):
    repo = test_env["repo"]
    canary = test_env["canary"]
    
    os.makedirs(os.path.join(repo, "a", "b"))
    symlink_path = os.path.join(repo, "a", "b", "evil")
    
    # relative to repo/a/b -> ../../../host/canary.txt
    # repo is at temp/repo, host is at temp/host
    rel_target = os.path.join("..", "..", "..", "host", "canary.txt")
    os.symlink(rel_target, symlink_path)
    
    with pytest.raises(ValueError, match="Symlinks are not allowed"):
        safe_read_text(repo, symlink_path)

def test_symlink_chain(test_env):
    repo = test_env["repo"]
    canary = test_env["canary"]
    
    # a -> b, b -> c, c -> canary
    a = os.path.join(repo, "a")
    b = os.path.join(repo, "b")
    c = os.path.join(repo, "c")
    
    os.symlink(canary, c)
    os.symlink("c", b)
    os.symlink("b", a)
    
    with pytest.raises(ValueError, match="Symlinks are not allowed"):
        safe_read_text(repo, a)

@pytest.mark.skipif(os.name == "nt", reason="FIFOs not perfectly supported on standard Windows")
def test_special_file(test_env):
    repo = test_env["repo"]
    fifo_path = os.path.join(repo, "test_fifo")
    try:
        os.mkfifo(fifo_path)
    except Exception:
        pytest.skip("Could not create FIFO")
        
    files_found = []
    for root, dirs, files, syms in safe_walk(repo):
        files_found.extend(files)
        
    assert "test_fifo" not in files_found

@pytest.mark.asyncio
async def test_pr_symlink_exploit(test_env):
    from tools.github_client import Github
    from agents.pr_author import agent_pr_author
    from tools.sandbox_runner import is_docker_available
    import subprocess
    import tools.github_client
    
    if not is_docker_available():
        pytest.skip("Docker required")
        
    repo = test_env["repo"]
    canary = test_env["canary"]
    
    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    
    symlink_path = os.path.join(repo, "secret.txt")
    os.symlink(canary, symlink_path)
    
    hooks_dir = os.path.join(repo, ".git", "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook = os.path.join(hooks_dir, "pre-push")
    
    host_hook_canary = os.path.join(test_env["host"], "hook_executed")
    
    with open(hook, "w") as f:
        f.write(f"#!/bin/sh\ntouch {host_hook_canary}\n")
    os.chmod(hook, 0o755)
    
    subprocess.run(["git", "add", "secret.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    
    state = {
        "repo_url": "https://github.com/test/symlink-malicious.git",
        "repo_local_path": repo,
        "repair_plan": [{"issue_id": "test", "file": "secret.txt", "action": "modify"}],
        "patches": [{"patch_id": "test", "file": "secret.txt", "applied": True}],
        "security_verified": True,
        "commit_sha": ""
    }
    
    # Mock github client
    class MockUser:
        login = "testuser"
        def create_fork(self, repo):
            class MockRepo:
                clone_url = repo
            return MockRepo()
            
    class MockRepo:
        owner = MockUser()
        def get_branch(self, *args): pass
        def create_pull(self, *args, **kwargs):
            class MockPR:
                html_url = "https://github.com/test/test/pull/1"
            return MockPR()

    class MockGithub:
        def __init__(self, token): pass
        def get_repo(self, name): return MockRepo()
        def get_user(self): return MockUser()

    original_github = tools.github_client.Github
    tools.github_client.Github = MockGithub
    
    dummy_remote = os.path.join(test_env["host"], "dummy_remote")
    os.makedirs(dummy_remote, exist_ok=True)
    subprocess.run(["git", "init", "--bare"], cwd=dummy_remote, check=True)
    
    # We mock prepare_repo_for_push to return our dummy_remote for pushing,
    # and create_trusted_pr_workspace to clone from the local repo instead of github.
    original_create_workspace = tools.github_client.create_trusted_pr_workspace
    original_prepare_repo = tools.github_client.prepare_repo_for_push
    
    def mock_create_workspace(url, token, sha):
        # Use the local repo as the clone source instead of the fake github URL
        return original_create_workspace(repo, token, sha)
        
    def mock_prepare_repo(url, workspace, token):
        # Setup dummy branch and push to local bare repo
        subprocess.run(["git", "checkout", "-b", "ai-fix-test"], cwd=workspace, check=True)
        return {
            "branch_name": "ai-fix-test",
            "push_repo_url": dummy_remote,
            "repo_name": "test/test",
            "is_owner": True,
            "user_login": "testuser"
        }
        
    tools.github_client.create_trusted_pr_workspace = mock_create_workspace
    tools.github_client.prepare_repo_for_push = mock_prepare_repo
    
    os.environ["GITHUB_TOKEN"] = "fake_test_token"
    
    import agents.pr_author
    original_groq_keys = agents.pr_author.GROQ_API_KEYS
    agents.pr_author.GROQ_API_KEYS = ["fake_key"]

    try:
        await agent_pr_author(state)
        
        # Verify hook was never executed
        assert not os.path.exists(host_hook_canary)
        
    finally:
        tools.github_client.Github = original_github
        tools.github_client.create_trusted_pr_workspace = original_create_workspace
        tools.github_client.prepare_repo_for_push = original_prepare_repo
        agents.pr_author.GROQ_API_KEYS = original_groq_keys

@pytest.mark.asyncio
async def test_static_analysis_symlink_reporting(test_env):
    repo = test_env["repo"]
    canary = test_env["canary"]
    
    os.symlink(canary, os.path.join(repo, "evil.txt"))
    
    state = {"repo_local_path": repo}
    result = await agent_static_analysis(state)
    
    findings = result.get("static_findings", [])
    symlink_findings = [f for f in findings if f["tool"] == "symlink_checker"]
    
    assert len(symlink_findings) > 0
    assert "evil.txt" in symlink_findings[0]["file"]
