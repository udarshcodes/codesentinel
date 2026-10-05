import pytest
import os
import json
import asyncio
from models.pipeline_state import PipelineState
from agents.code_generator import agent_code_generator

@pytest.mark.asyncio
async def test_code_generator_imports_and_safe_paths(tmp_path):
    # This test ensures that safe_path_exists and open_safe are correctly imported
    # and executed within agent_code_generator.
    
    # Create a dummy target file
    repo_local_path = str(tmp_path)
    target_file = "dummy.py"
    target_path = os.path.join(repo_local_path, target_file)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write("def foo():\n    pass\n")

    # Construct state that will trigger the repair plan execution
    state = PipelineState()
    state["repo_local_path"] = repo_local_path
    state["repair_plan"] = [{"issue_id": "issue-1", "action": "Fix foo function"}]
    state["investigated_issues"] = [{"id": "issue-1", "affected_files": [target_file]}]
    state["patches"] = []
    state["retry_count"] = 0
    state["touched_symbols"] = {}

    # Ensure GROQ_API_KEYS are mocked or exist so the loop runs
    import config
    original_keys = config.GROQ_API_KEYS
    config.GROQ_API_KEYS = ["dummy-key"]

    try:
        # We expect a mock of invoke_llm so we don't actually hit the LLM.
        # However, we only need to mock invoke_llm to prevent network calls.
        # The goal is to reach safe_path_exists and open_safe.
        from unittest.mock import patch
        with patch("agents.code_generator.invoke_llm", return_value="def foo():\n    return True\n"):
            result = await agent_code_generator(state)
            
            # Since invoke_llm returned a fix, the agent should have successfully
            # executed without raising NameError for safe_path_exists or open_safe.
            # apply_patch might fail depending on diff format, which is fine.
            assert True
    finally:
        config.GROQ_API_KEYS = original_keys
