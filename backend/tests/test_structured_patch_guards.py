import json
from unittest.mock import patch
import pytest

from tools.patch_applier import apply_patch
from tools.remediations import python_dependency_patch, npm_dependency_patch


@pytest.mark.parametrize('name,original,replacement', [
    ('pyproject.toml', '[project]\nname="example"\n', '[project]\nname=[\n'),
    ('uv.lock', 'version=1\n', 'version=[\n'),
    ('package.json', '{"name":"example"}\n', '{"name":}\n'),
])
def test_invalid_structured_patch_never_mutates_the_manifest(tmp_path, name, original, replacement):
    target = tmp_path / name
    target.write_text(original)
    result = apply_patch('<<<SEARCH>>>\n' + original + '<<<REPLACE>>>\n' + replacement, str(tmp_path), name)
    assert not result['success']
    assert 'syntax error' in result['stderr']
    assert target.read_text() == original


@pytest.mark.parametrize('name', ['requirements.txt', 'pyproject.toml'])
def test_verified_python_update_preserves_extras_and_markers(tmp_path, name):
    from packaging.requirements import Requirement
    import tomllib
    requirement = "example[feature]==1.0.0; python_version >= '3.9'"
    original = requirement + '\n' if name == 'requirements.txt' else '[project]\ndependencies=[' + json.dumps(requirement) + ']\n'
    target = tmp_path / name
    target.write_text(original)
    finding = {'package': 'example', 'current_version': '1.0.0', 'recommended_version': '1.2.0'}
    generated = python_dependency_patch(original, name, finding)
    assert apply_patch(generated, str(tmp_path), name)['success']
    updated = target.read_text()
    value = updated.strip() if name == 'requirements.txt' else tomllib.loads(updated)['project']['dependencies'][0]
    parsed = Requirement(value)
    assert str(parsed.specifier) == '==1.2.0'
    assert parsed.extras == {'feature'} and parsed.marker is not None
    assert python_dependency_patch(updated, name, finding) is None


def test_repeating_a_verified_npm_update_does_not_reject_the_previous_patch():
    finding = {'package': 'example', 'current_version': '1.0.0', 'recommended_version': '1.2.0'}
    assert npm_dependency_patch('{"dependencies":{"example":"1.2.0"}}', 'package.json', finding) is None


@pytest.mark.asyncio
async def test_bad_manifest_syntax_is_repairable_not_an_infrastructure_outage(tmp_path):
    from agents.validator import agent_validator
    from orchestrator import OrchestratorAgent
    state = {'repo_local_path': str(tmp_path), 'patches': [{'patch_id': 7, 'file': 'pyproject.toml', 'applied': True}]}
    with patch('tools.project_dependencies.prepare_python_dependencies', return_value={'status': 'failed', 'error': 'TOMLDecodeError: Invalid value'}):
        result = await agent_validator(state)
    latest = result['validation_results'][-1]
    assert latest['build_failed'] and not latest['infrastructure_error']
    assert latest['failed_issue_ids'] == [7] and result['retry_count'] == 1
    assert OrchestratorAgent.route_after_validator({**state, **result}) == 'code_generator'
