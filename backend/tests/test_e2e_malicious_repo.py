import os
import sys
import shutil
import tempfile
import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")

import subprocess
@pytest.fixture
def e2e_env():
    temp_base = tempfile.mkdtemp(prefix="e2e_malicious_")
    
    host_dir = os.path.join(temp_base, "host")
    os.makedirs(host_dir)
    canary = os.path.join(host_dir, "canary.txt")
    with open(canary, "w") as f:
        f.write("SECRET_HOST_INFO")
        
    repo_dir = os.path.join(temp_base, "repo")
    os.makedirs(repo_dir)
    
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo_dir, check=True)
    
    # Symlink to canary
    os.symlink(canary, os.path.join(repo_dir, "app.py"))
    
    # Directory symlink
    os.symlink(host_dir, os.path.join(repo_dir, "config"))
    
    subprocess.run(["git", "add", "app.py", "config"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)
    
    yield {
        "base": temp_base,
        "repo": repo_dir,
        "host": host_dir,
        "canary": canary
    }
    
    shutil.rmtree(temp_base, ignore_errors=True)

@pytest.mark.asyncio
async def test_e2e_repo_mapper_malicious(e2e_env):
    from agents.repo_mapper import agent_repo_mapper
    import agents.repo_mapper
    
    repo = e2e_env["repo"]
    
    state = {
        "repo_url": "https://github.com/test/malicious",
    }
    
    original_re_match = agents.repo_mapper.re.match
    def mocked_re_match(pattern, string, *args, **kwargs):
        if "github.com" in pattern:
            return True
        return original_re_match(pattern, string, *args, **kwargs)
    agents.repo_mapper.re.match = mocked_re_match
    
    original_run = agents.repo_mapper.subprocess.run
    def hooked_run(cmd, *args, **kwargs):
        if cmd[0] == "git" and cmd[1] == "clone":
            cmd[3] = repo
        return original_run(cmd, *args, **kwargs)
    agents.repo_mapper.subprocess.run = hooked_run

    try:
        result = await agent_repo_mapper(state)
        
        kg = result.get("knowledge_graph", {})
        
        # Validate the results didn't leak host info
        assert "SECRET_HOST_INFO" not in str(kg)
        
    finally:
        agents.repo_mapper.re.match = original_re_match
        agents.repo_mapper.subprocess.run = original_run
