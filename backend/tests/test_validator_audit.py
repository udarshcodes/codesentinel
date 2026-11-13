from unittest.mock import patch

import pytest
from agents.validator import agent_validator


@pytest.mark.asyncio
async def test_missing_build_tool_does_not_pass_validation(tmp_path):
    (tmp_path / "setup.py").write_text('from setuptools import setup\nsetup(name="example")\n')
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


@pytest.mark.asyncio
async def test_python_syntax_validation_uses_container_interpreter(tmp_path):
    from tools.sandbox_runner import is_docker_available
    if not is_docker_available():
        pytest.skip("Docker is required for real interpreter validation")
    (tmp_path / "app.py").write_text("value = 42\n")
    result = await agent_validator({"repo_local_path": str(tmp_path),
                                    "patches": [{"file": "app.py", "applied": True}]})
    validation = result["validation_results"][-1]
    assert "[PASSED] app.py - syntax OK" in validation["logs"]
    assert validation["passed"] is True


@pytest.mark.asyncio
async def test_later_success_supersedes_rejected_attempt_without_inflating_file_counts(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")
    state = {"repo_local_path": str(tmp_path), "patches": [
        {"patch_id": 7, "file": "app.py", "applied": False},
        {"patch_id": 7, "file": "app.py", "applied": True},
    ]}
    with patch("agents.validator.run_sandboxed_subprocess", return_value={"status": "SUCCESS", "stdout": "", "stderr": ""}):
        result = await agent_validator(state)
    validation = result["validation_results"][-1]
    assert validation["passed"] is True
    assert validation["files_validated"] == validation["files_passed"] == 1


@pytest.mark.asyncio
async def test_missing_configured_test_runner_cannot_pass(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")
    def run(cmd, **kwargs):
        return {"status": "SUCCESS" if "py_compile" in cmd else "UNAVAILABLE", "stdout": "", "stderr": "runner not found"}
    with patch("agents.validator.run_sandboxed_subprocess", side_effect=run):
        result = await agent_validator({"repo_local_path": str(tmp_path), "patches": [{"file": "app.py", "applied": True}], "knowledge_graph": {"test_framework": "pytest"}})
    assert result["validation_results"][-1]["passed"] is False


@pytest.mark.asyncio
async def test_app_only_pyproject_does_not_trigger_package_build(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="app"\nrequires-python=">=3.11"\n')
    (tmp_path / "app.py").write_text("value = 1\n")
    def run(cmd, **kwargs):
        assert "build" not in cmd
        return {"status": "SUCCESS", "stdout": "passed", "stderr": ""}
    with patch("agents.validator.run_sandboxed_subprocess", side_effect=run):
        result = await agent_validator({"repo_local_path": str(tmp_path), "patches": [{"file": "app.py", "applied": True}]})
    assert result["validation_results"][-1]["build_failed"] is False
