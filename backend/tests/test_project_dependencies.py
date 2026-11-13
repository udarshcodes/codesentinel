from unittest.mock import patch
import pytest
from tools.project_dependencies import python_requirements, prepare_python_dependencies
from orchestrator import OrchestratorAgent


@pytest.mark.parametrize('value', ['-r secret.txt', '--index-url https://example.invalid', 'example @ https://example.invalid/package.whl', '-e .'])
def test_dependency_preparation_rejects_non_registry_inputs_before_launch(tmp_path, value):
    (tmp_path / 'requirements.txt').write_text(value)
    with patch('tools.project_dependencies.subprocess.run') as launch:
        result = prepare_python_dependencies(str(tmp_path))
    assert result['status'] == 'failed'
    launch.assert_not_called()


def test_project_and_test_dependencies_are_read_without_running_setup(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\ndependencies=["requests==2.32.3"]\n[project.optional-dependencies]\ntest=["pytest>=9"]\n')
    assert python_requirements(str(tmp_path)) == ['pytest>=9', 'requests==2.32.3']


def test_missing_wheels_are_infrastructure_errors_not_an_llm_repair_request():
    state = {'validation_results': [{'passed': False, 'infrastructure_error': True}], 'patches': [{'applied': True}]}
    assert OrchestratorAgent.route_after_validator(state) == 'pr_author'
