import os
import pytest
from models.pipeline_state import PipelineState

@pytest.mark.asyncio
async def test_repo_mapper_git_isolation(monkeypatch):
    import agents.repo_mapper
    
    monkeypatch.setenv("GITHUB_TOKEN", "TEST_GITHUB_SECRET")
    
    state = PipelineState({
        "repo_url": "https://github.com/test/repo",
        "commit_sha": "abc1234"
    })
    
    invocations = []
    
    original_run = agents.repo_mapper.subprocess.run
    def mock_run(cmd, *args, **kwargs):
        invocations.append({
            "cmd": cmd,
            "env": kwargs.get("env", {})
        })
        # Mock git clone and others
        class MockRes:
            stdout = "mock_file.py"
        return MockRes()
        
    monkeypatch.setattr(agents.repo_mapper.subprocess, "run", mock_run)
    
    # Mock knowledge graph build to avoid running RAG and other things
    def mock_build_knowledge_graph(*args, **kwargs):
        class MockKG:
            def to_dict(self): return {}
        return MockKG()
        
    monkeypatch.setattr("tools.knowledge_graph.build_knowledge_graph", mock_build_knowledge_graph)
    
    # Mock LLM
    async def mock_invoke_llm(*args, **kwargs):
        return {"language": "python"}
    monkeypatch.setattr(agents.repo_mapper, "invoke_llm", mock_invoke_llm)
    
    await agents.repo_mapper.agent_repo_mapper(state)
    
    assert len(invocations) == 3, "Expected clone, checkout, and ls-files"
    
    clone_inv = invocations[0]
    assert clone_inv["cmd"][0] == "git"
    assert clone_inv["cmd"][1] == "clone"
    assert "--no-checkout" in clone_inv["cmd"]
    assert "TEST_GITHUB_SECRET" not in str(clone_inv["cmd"])
    
    # Verify clone environment
    clone_env = clone_inv["env"]
    assert "GIT_CONFIG_VALUE_0" in clone_env
    assert "TEST_GITHUB_SECRET" in clone_env["GIT_CONFIG_VALUE_0"]
    assert "GITHUB_TOKEN" not in clone_env
    
    checkout_inv = invocations[1]
    assert checkout_inv["cmd"][0] == "git"
    assert "-c" in checkout_inv["cmd"]
    assert "core.hooksPath=/dev/null" in checkout_inv["cmd"]
    assert "checkout" in checkout_inv["cmd"]
    
    checkout_env = checkout_inv["env"]
    assert "GITHUB_TOKEN" not in checkout_env
    assert "GH_TOKEN" not in checkout_env
    assert "TEST_GITHUB_SECRET" not in str(checkout_env)
    assert "GIT_CONFIG_VALUE_0" not in checkout_env
    
    ls_inv = invocations[2]
    assert ls_inv["cmd"][0] == "git"
    assert "-c" in ls_inv["cmd"]
    assert "core.hooksPath=/dev/null" in ls_inv["cmd"]
    assert "ls-files" in ls_inv["cmd"]
    
    ls_env = ls_inv["env"]
    assert "GITHUB_TOKEN" not in ls_env
    assert "GH_TOKEN" not in ls_env
    assert "TEST_GITHUB_SECRET" not in str(ls_env)
    assert "GIT_CONFIG_VALUE_0" not in ls_env

def test_proc_credential_isolation(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "TEST_GITHUB_SECRET")
    
    from tools.subprocess_runner import get_safe_env
    safe_env = get_safe_env(keep_github_token=False)
    
    assert "GITHUB_TOKEN" not in safe_env
    assert "TEST_GITHUB_SECRET" not in str(safe_env)
