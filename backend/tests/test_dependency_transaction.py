from unittest.mock import patch

import pytest

from tools.dependency_transaction import capture_manifest, rollback_dependencies


def transaction(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["example==1.0"]\n')
    (tmp_path / "uv.lock").write_text('version=1\n')
    originals = {}
    capture_manifest(str(tmp_path), "pyproject.toml", originals)
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["example==2.0"]\n')
    (tmp_path / "uv.lock").write_text('version=2\n')
    capture_manifest(str(tmp_path), "pyproject.toml", originals)
    return {"repo_local_path": str(tmp_path), "manifest_originals": originals,
            "patches": [{"patch_id": "dependency", "file": "pyproject.toml", "applied": True},
                        {"patch_id": "source", "file": "app.py", "applied": True}],
            "investigated_issues": [{"id": "dependency", "severity": "high", "affected_files": ["pyproject.toml"]}],
            "repair_plan": [{"issue_id": "dependency"}, {"issue_id": "source"}]}


def test_rollback_restores_original_pair_and_retains_source_repair(tmp_path):
    state = transaction(tmp_path)
    result = rollback_dependencies(state, ["pyproject.toml"], "Incompatible versions")
    assert 'example==1.0' in (tmp_path / "pyproject.toml").read_text()
    assert (tmp_path / "uv.lock").read_text() == 'version=1\n'
    assert result["patches"][0]["excluded_from_validation"]
    assert not result["patches"][0]["applied"]
    assert result["patches"][1]["applied"]
    assert result["repair_plan"] == [{"issue_id": "source"}]
    assert result["investigated_issues"][0]["remediation_mode"] == "manual_review"
    assert state["patches"][0]["applied"]  # History input is not mutated.


def test_missing_baseline_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="baseline"):
        rollback_dependencies({"repo_local_path": str(tmp_path)}, ["package.json"], "Conflict")


@pytest.mark.asyncio
async def test_generator_rolls_back_lock_resolution_failure(tmp_path):
    from agents.code_generator import agent_code_generator
    state = transaction(tmp_path)
    state["repair_plan"] = [{"issue_id": "dependency"}]
    state["retry_count"] = 1
    with patch('agents.code_generator.GROQ_API_KEYS', ['test']), patch('tools.uv_lock_repair.synchronize_uv_lock', side_effect=RuntimeError('incompatible dependency constraints')):
        result = await agent_code_generator(state)
    assert not result["patches"][0]["applied"]
    assert result["patches"][1]["applied"]
    assert result["dependency_blocked_files"] == ["pyproject.toml"]
    assert 'example==1.0' in (tmp_path / "pyproject.toml").read_text()


@pytest.mark.asyncio
async def test_all_dependency_patches_rolled_back_do_not_loop(tmp_path):
    from agents.validator import agent_validator
    from orchestrator import OrchestratorAgent
    state = transaction(tmp_path)
    state["patches"] = state["patches"][:1]
    with patch('tools.project_dependencies.prepare_python_dependencies', return_value={"status": "failed", "error": "ResolutionImpossible: conflicting dependencies"}) as prepare:
        result = await agent_validator(state)
    assert prepare.call_count == 1
    assert result["dependency_blocked_files"]
    assert OrchestratorAgent.route_after_validator({**state, **result}) == "pr_author"
