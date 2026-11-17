"""Regenerate uv locks for static, registry-only Python application manifests.

The online resolver sees only sanitized metadata, a lock and a trusted uv
executable. Repository source, build backends, configuration and secrets are
never mounted into this container.
"""
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import uuid
from urllib.parse import urlsplit

from packaging.requirements import Requirement
from tools.patch_applier import apply_patch
from tools.safe_repo import safe_read_text


def registry_requirements(values):
    if not isinstance(values, list) or len(values) > 128:
        raise ValueError('Expected at most 128 ordinary registry dependencies.')
    for value in values:
        requirement = Requirement(value)
        if requirement.url:
            raise ValueError('URL, local and VCS dependencies require a prepared lockfile.')
    return values


def lock_manifest(text):
    data = tomllib.loads(text)
    project = data.get('project', {})
    tool = data.get('tool', {}).get('uv', {})
    if data.get('build-system') or project.get('dynamic') or tool:
        raise ValueError('Automatic uv lock repair requires a static application manifest without build hooks, workspaces or custom sources.')
    if not project.get('name') or not project.get('version'):
        raise ValueError('Static project name and version are required for automatic uv lock repair.')
    lines = ['[project]']
    for name in ['name', 'version', 'requires-python']:
        if name in project:
            if not isinstance(project[name], str):
                raise ValueError('Project metadata must contain literal strings.')
            lines.append(f'{name} = {json.dumps(project[name])}')
    lines.append('dependencies = ' + json.dumps(registry_requirements(project.get('dependencies', []))))
    for section, groups in [('project.optional-dependencies', project.get('optional-dependencies', {})),
                            ('dependency-groups', data.get('dependency-groups', {}))]:
        if groups:
            lines.append('[' + section + ']')
            for name, values in groups.items():
                lines.append(json.dumps(name) + ' = ' + json.dumps(registry_requirements(values)))
    return '\n'.join(lines) + '\n'


def validate_lock(text):
    if len(text.encode()) > 1024 * 1024 or '<<<' in text:
        raise ValueError('uv lock exceeds the safe repair journal limit.')
    data = tomllib.loads(text)
    if not data.get('package'):
        raise ValueError('uv produced an empty lockfile.')
    for package in data['package']:
        source = package.get('source', {})
        if source not in ({'registry': 'https://pypi.org/simple'}, {'virtual': '.'}):
            raise ValueError('uv lock contains an unsupported package source.')
        for artifact in package.get('wheels', []) + ([package['sdist']] if package.get('sdist') else []):
            url = urlsplit(artifact.get('url', ''))
            if (url.scheme != 'https' or url.hostname != 'files.pythonhosted.org' or url.username
                    or url.password or url.port not in (None, 443) or not artifact.get('hash', '').startswith('sha256:')):
                raise ValueError('uv lock artifacts must use hashed official PyPI downloads.')
    return data


def synchronize_uv_lock(repo, manifest_path):
    relative = PurePosixPath(manifest_path.replace('\\', '/'))
    if relative.name != 'pyproject.toml':
        return None
    target = str(relative.parent / 'uv.lock')
    manifest = lock_manifest(safe_read_text(repo, str(relative)))
    original = safe_read_text(repo, target)
    original_data = validate_lock(original)
    from tools.python_runtime import prepare_project_runtime
    project = str(relative.parent)
    runtime = prepare_project_runtime(os.path.join(repo, project))
    executable = shutil.which('uv')
    if not executable:
        raise RuntimeError('The worker requires the trusted uv executable to repair uv locks.')
    image = os.getenv('SANDBOX_IMAGE', 'ghcr.io/udarshcodes/codesentinel-sandbox:latest')
    if os.getenv('ENVIRONMENT') == 'production' and '@sha256:' not in image:
        raise ValueError('Lock regeneration requires an immutable production image.')
    with tempfile.TemporaryDirectory(prefix='codesentinel_uv_lock_') as temporary:
        workspace = Path(temporary)
        (workspace / 'pyproject.toml').write_text(manifest, encoding='utf-8')
        (workspace / 'uv.lock').write_text(original, encoding='utf-8')
        user = f'{os.getuid()}:{os.getgid()}' if hasattr(os, 'getuid') else '1000:1000'
        container = 'codesentinel-uv-lock-' + uuid.uuid4().hex
        command = ['docker', 'run', '--rm', '--name', container, '--read-only', '--cap-drop=ALL',
                   '--security-opt=no-new-privileges', '--memory=2g', '--pids-limit=128', '--user', user,
                   '--tmpfs', '/tmp:size=512m', '--network', 'bridge', '-e', 'HOME=/tmp',
                   '-v', f'{workspace}:/deps', '-v', f'{os.path.realpath(executable)}:/opt/codesentinel/uv:ro',
                   '-w', '/deps', image, '/opt/codesentinel/uv', 'lock', '--no-config', '--no-sources',
                   '--no-build', '--no-python-downloads', '--python', runtime['executable'] if runtime else 'python', '--default-index',
                   'https://pypi.org/simple', '--cache-dir', '/tmp/uv-cache']
        if runtime:
            command[command.index(image):command.index(image)] = ['-v', f"{runtime['root']}:/opt/codesentinel/project-python:ro"]
        environment = {key: value for key, value in os.environ.items() if key.upper() in
                       {'PATH', 'DOCKER_CONFIG', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'SYSTEMROOT', 'TEMP', 'TMP'}}
        try:
            result = subprocess.run(command, cwd=workspace, env=environment, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=180)
        finally:
            subprocess.run(['docker', 'rm', '-f', container], env=environment, capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError('uv lock regeneration failed: ' + (result.stdout + result.stderr)[-4000:])
        generated = (workspace / 'uv.lock').read_text(encoding='utf-8')
        if validate_lock(generated) == original_data:
            return None
    patch = '<<<SEARCH>>>\n' + original.strip('\n') + '\n<<<REPLACE>>>\n' + generated.strip('\n') + '\n'
    result = apply_patch(patch, repo, target)
    if not result['success']:
        raise RuntimeError('Cannot journal generated uv lock: ' + result['stderr'])
    return {'patch_id': 'lockfile:' + target, 'file': target, 'applied': True, 'patch_text': patch,
            'diff': ''.join(difflib.unified_diff(original.splitlines(True), generated.splitlines(True),
                                              fromfile=target, tofile=target)), 'generated_by': 'uv'}
