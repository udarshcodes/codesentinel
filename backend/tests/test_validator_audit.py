from unittest.mock import patch

import pytest
from agents.validator import agent_validator


@pytest.mark.asyncio
async def test_generated_npm_peer_conflict_retries_manifest_repair(tmp_path):
    (tmp_path / 'package.json').write_text('{"devDependencies":{"vite":"5.0.0"}}')
    with patch('tools.node_dependencies.prepare_node_dependencies', return_value={'status':'failed', 'error':'npm ERESOLVE incompatible peer dependency'}):
        result = await agent_validator({'repo_local_path':str(tmp_path), 'patches':[{'patch_id':15, 'file':'package.json', 'applied':True}]})
    validation = result['validation_results'][-1]
    assert validation['passed'] is False
    assert validation['infrastructure_error'] is False
    assert validation['failed_issue_ids'] == [15]


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


@pytest.mark.asyncio
async def test_node_dependency_failure_is_infrastructure_and_stops_build(tmp_path):
    (tmp_path / "app.js").write_text("const value = 1;")
    (tmp_path / "package.json").write_text('{"scripts":{"build":"vite build"}}')
    (tmp_path / "package-lock.json").write_text('{}')
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return {"status": "FAILED" if cmd[0] == "npm" else "SUCCESS", "stdout": "", "stderr": "cache unavailable"}
    with patch("agents.validator.run_sandboxed_subprocess", side_effect=run):
        result = await agent_validator({"repo_local_path": str(tmp_path), "patches": [{"file": "app.js", "applied": True}]})
    assert result["validation_results"][-1]["infrastructure_error"] is True
    assert not [c for c in calls if c[0] == "npm"]


@pytest.mark.asyncio
async def test_configured_node_lint_is_required_for_validation(tmp_path):
    (tmp_path / "app.js").write_text("const value = 1;")
    (tmp_path / "package.json").write_text('{"scripts":{"build":"vite build","lint":"eslint ."}}')
    commands = []
    def run(cmd, **kwargs):
        commands.append(cmd)
        return {"status": "FAILED" if cmd == ["npm", "run", "lint"] else "SUCCESS", "stdout": "", "stderr": "lint error"}
    with patch("agents.validator.run_sandboxed_subprocess", side_effect=run), patch("tools.node_dependencies.prepare_node_dependencies", return_value={"status": "ready"}):
        result = await agent_validator({"repo_local_path": str(tmp_path), "patches": [{"file": "app.js", "applied": True}]})
    assert ["npm", "run", "build"] in commands
    assert ["npm", "run", "lint"] in commands
    assert result["validation_results"][-1]["passed"] is False
    assert result["validation_results"][-1]["build_failed"] is True


@pytest.mark.asyncio
async def test_jsx_is_covered_by_real_project_build_not_failed_before_it_runs(tmp_path):
    (tmp_path / "App.jsx").write_text("export default () => <p>hello</p>;")
    (tmp_path / "package.json").write_text('{"scripts":{"build":"vite build","lint":"eslint ."}}')
    with patch("agents.validator.run_sandboxed_subprocess", return_value={"status": "SUCCESS", "stdout": "", "stderr": ""}), patch(
        "tools.node_dependencies.prepare_node_dependencies", return_value={"status": "ready"}):
        result = await agent_validator({"repo_local_path": str(tmp_path), "patches": [{"file": "App.jsx", "applied": True}]})
    validation = result["validation_results"][-1]
    assert validation["passed"] is True
    assert validation["files_passed"] == 1
    assert validation["tests_executed"] is False


@pytest.mark.asyncio
async def test_jsx_without_project_build_cannot_be_claimed_as_validated(tmp_path):
    (tmp_path / "App.jsx").write_text("export default () => <p>hello</p>;")
    result = await agent_validator({"repo_local_path": str(tmp_path), "patches": [{"file": "App.jsx", "applied": True}]})
    assert result["validation_results"][-1]["passed"] is False
