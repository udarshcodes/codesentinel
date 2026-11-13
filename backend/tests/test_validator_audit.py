from unittest.mock import patch

import pytest
from agents.validator import agent_validator


@pytest.mark.asyncio
async def test_missing_build_tool_does_not_pass_validation(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="example"\n')
    (tmp_path / "app.py").write_text('x = 1\n')
    state = {"repo_local_path": str(tmp_path), "patches": [{"file": "app.py", "applied": True}]}
    def run(cmd, **kwargs):
        if "py_compile" in cmd:
            return {"status": "SUCCESS", "stdout": "", "stderr": ""}
        return {"status": "FAILED", "stdout": "", "stderr": "No module named build"}
    with patch("agents.validator.run_sandboxed_subprocess", side_effect=run):
        result = await agent_validator(state)
    assert result["validation_results"][-1]["passed"] is False
    assert result["validation_results"][-1]["build_failed"] is True


@pytest.mark.asyncio
async def test_missing_patched_file_does_not_pass_validation(tmp_path):
    result = await agent_validator({"repo_local_path": str(tmp_path),
                                    "patches": [{"file": "missing.py", "applied": True}]})
    assert result["validation_results"][-1]["passed"] is False
