"""Honor repository Python declarations without executing repository code online."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
try:
    import tomllib
except ImportError:
    import tomli as tomllib

from packaging.specifiers import SpecifierSet
from tools.safe_repo import safe_path_exists, safe_read_text

_runtimes = {}
IMAGE_PYTHON = os.getenv('SANDBOX_PYTHON_VERSION', '3.12.3')


def runtime_selection(repo):
    constraint = SpecifierSet()
    if safe_path_exists(repo, 'pyproject.toml'):
        project = tomllib.loads(safe_read_text(repo, 'pyproject.toml')).get('project', {})
        constraint = SpecifierSet(project.get('requires-python', ''))
    if safe_path_exists(repo, '.python-version'):
        requested = safe_read_text(repo, '.python-version').strip()
        if not re.fullmatch(r'3\.(?:9|1[0-5])(?:\.\d{1,3})?', requested):
            raise ValueError('A single stable CPython 3.9–3.15 version is required in .python-version.')
        version = requested if requested.count('.') == 2 else requested + '.999'
        if not constraint.contains(version):
            raise ValueError('.python-version conflicts with the declared requires-python range.')
        if (requested == IMAGE_PYTHON or requested == '.'.join(IMAGE_PYTHON.split('.')[:2])) and constraint.contains(IMAGE_PYTHON):
            return None, constraint
        return requested, constraint
    if constraint.contains(IMAGE_PYTHON):
        return None, constraint
    for minor in range(15, 8, -1):
        if constraint.contains(f'3.{minor}.999'):
            return f'3.{minor}', constraint
    raise ValueError('The declared Python range needs an operator-prepared runtime.')


def prepare_project_runtime(repo):
    from tools.sandbox_runner import register_project_runtime, clear_project_runtime
    requested, constraint = runtime_selection(repo)
    if requested is None:
        clear_project_runtime(repo)
        return None
    if sys.platform != 'linux':
        raise RuntimeError('Managed alternate runtimes require a Linux worker.')
    if requested not in _runtimes:
        executable = shutil.which('uv')
        if not executable:
            raise RuntimeError('The trusted uv executable is required to prepare the declared Python runtime.')
        temporary = tempfile.TemporaryDirectory(prefix='codesentinel_python_')
        workspace = Path(temporary.name)
        environment = {key: value for key, value in os.environ.items() if key.upper() in {'PATH', 'TEMP', 'TMP'}}
        environment.update({'HOME': str(workspace), 'UV_PYTHON_INSTALL_DIR': str(workspace / 'runtimes'),
                            'UV_CACHE_DIR': str(workspace / 'cache'), 'UV_PYTHON_BIN_DIR': str(workspace / 'bin')})
        # uv receives only a validated version, a clean environment and an empty
        # working directory. Its official CPython distribution is the only download.
        install = subprocess.run([executable, 'python', 'install', '--no-config', '--no-bin', requested],
                                 cwd=workspace, env=environment, capture_output=True, text=True, timeout=180)
        if install.returncode:
            raise RuntimeError('Declared Python runtime download failed: ' + install.stderr[-1200:])
        found = subprocess.run([executable, 'python', 'find', '--no-config', '--managed-python', '--no-python-downloads', requested],
                               cwd=workspace, env=environment, capture_output=True, text=True, timeout=30)
        if found.returncode:
            raise RuntimeError('The declared managed Python interpreter could not be located.')
        interpreter = Path(found.stdout.strip()).resolve()
        root = interpreter.parent.parent
        if not interpreter.is_file() or not interpreter.is_relative_to(workspace):
            raise RuntimeError('Managed interpreter escaped its isolated installation directory.')
        version = re.search(r'cpython-(\d+\.\d+\.\d+)', root.name)
        if not version:
            raise RuntimeError('Cannot verify the managed CPython version.')
        # pip is trusted tooling copied from the worker, not from the repository.
        # Mounting only pip avoids mixing the image's native Python 3.12 packages
        # into an older interpreter during wheel resolution and installation.
        import pip
        tools = workspace / 'tools'
        shutil.copytree(Path(pip.__file__).parent, tools / 'pip')
        runtime = {'root': str(root), 'executable': '/opt/codesentinel/project-python/bin/' + interpreter.name,
                   'pip_tools': str(tools), 'version': version.group(1)}
        _runtimes[requested] = runtime, temporary
    runtime = _runtimes[requested][0]
    if not constraint.contains(runtime['version']):
        raise ValueError('The available managed interpreter does not satisfy requires-python.')
    register_project_runtime(repo, runtime)
    return runtime
