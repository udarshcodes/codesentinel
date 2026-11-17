import os
import shutil
from unittest.mock import patch
import pytest

from tools.python_runtime import runtime_selection


@pytest.mark.parametrize('pin', ['3.10', '3.11', '3.13', '3.14.2'])
def test_repository_python_pin_is_honored_without_project_execution(tmp_path, pin):
    (tmp_path / '.python-version').write_text(pin + '\n')
    assert runtime_selection(str(tmp_path))[0] == pin


@pytest.mark.parametrize('pin', ['3.11; echo bad', 'https://example.invalid/python', '3.11\n3.12', '../python'])
def test_runtime_requests_are_versions_not_commands_or_download_urls(tmp_path, pin):
    from tools.python_runtime import prepare_project_runtime
    (tmp_path / '.python-version').write_text(pin)
    with patch('tools.python_runtime.subprocess.run') as launch:
        with pytest.raises(ValueError):
            prepare_project_runtime(str(tmp_path))
    launch.assert_not_called()


def test_python_range_is_respected_without_a_version_file(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nrequires-python=">=3.10,<3.12"\n')
    assert runtime_selection(str(tmp_path))[0] == '3.11'
    (tmp_path / '.python-version').write_text('3.13')
    with pytest.raises(ValueError, match='conflicts'):
        runtime_selection(str(tmp_path))


@pytest.mark.skipif(not shutil.which('docker') or not shutil.which('uv') or not os.getenv('SANDBOX_IMAGE'), reason='Requires the CI sandbox and trusted uv')
def test_native_wheels_and_tests_use_the_declared_runtime_while_scanners_stay_isolated(tmp_path):
    from tools.project_dependencies import prepare_python_dependencies
    from tools.sandbox_runner import run_sandboxed_subprocess
    (tmp_path / '.python-version').write_text('3.11\n')
    (tmp_path / 'requirements.txt').write_text('numpy<2\nchroma-hnswlib==0.7.3\npytest==8.2.2\n')
    result = prepare_python_dependencies(str(tmp_path))
    assert result['status'] == 'ready', result
    assert result['python_version'].startswith('3.11.')
    native = run_sandboxed_subprocess(['python', '-c', 'import sys,hnswlib; assert sys.version_info[:2] == (3,11); print("native import passed")'], cwd=str(tmp_path))
    assert native['status'] == 'SUCCESS', native
    tests = run_sandboxed_subprocess(['python', '-m', 'pytest', '--version'], cwd=str(tmp_path))
    assert tests['status'] == 'SUCCESS' and '8.2.2' in tests['stdout'], tests
    scanner = run_sandboxed_subprocess(['python', '-m', 'pylint', '--version'], cwd=str(tmp_path))
    assert scanner['status'] == 'SUCCESS', scanner
