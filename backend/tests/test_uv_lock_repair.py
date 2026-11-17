import os
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import patch
import pytest

from tools.uv_lock_repair import lock_manifest, validate_lock, synchronize_uv_lock


MANIFEST = '[project]\nname="example"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=["idna==3.19"]\n'
LOCK = 'version = 1\nrevision = 3\nrequires-python = ">=3.12"\n[[package]]\nname="example"\nversion="0.1.0"\nsource={virtual="."}\n'


@pytest.mark.parametrize('extra', [
    '\n[build-system]\nrequires=["evil"]\nbuild-backend="evil"\n',
    '\n[tool.uv.sources]\nidna={git="https://example.invalid/code"}\n',
    '\n[tool.uv.workspace]\nmembers=["packages/*"]\n',
])
def test_online_resolver_rejects_repository_execution_and_custom_sources(extra):
    with pytest.raises(ValueError):
        lock_manifest(MANIFEST + extra)


def test_lock_download_urls_cannot_override_registry_allowlist():
    with pytest.raises(ValueError, match='official PyPI'):
        validate_lock(LOCK + 'wheels=[{url="https://example.invalid/package.whl",hash="sha256:abc"}]\n')


def test_generated_lock_is_replayable_on_a_fresh_trusted_checkout(tmp_path):
    (tmp_path / 'pyproject.toml').write_text(MANIFEST)
    (tmp_path / 'uv.lock').write_text(LOCK)
    generated = LOCK + '\n[[package]]\nname="idna"\nversion="3.19"\nsource={registry="https://pypi.org/simple"}\n'

    def resolve(command, **kwargs):
        if 'lock' in command:
            Path(kwargs['cwd'], 'uv.lock').write_text(generated)
            assert '--no-build' in command and '--no-sources' in command
            assert str(tmp_path) not in ' '.join(command)
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    with patch('tools.uv_lock_repair.shutil.which', return_value='/trusted/uv'), patch('tools.uv_lock_repair.subprocess.run', side_effect=resolve):
        result = synchronize_uv_lock(str(tmp_path), 'pyproject.toml')
    assert result['applied']
    assert 'idna' in (tmp_path / 'uv.lock').read_text()
    from tools.patch_applier import apply_patch
    (tmp_path / 'uv.lock').write_text(LOCK)
    assert apply_patch(result['patch_text'], str(tmp_path), 'uv.lock')['success']
    assert validate_lock((tmp_path / 'uv.lock').read_text()) == validate_lock(generated)


@pytest.mark.skipif(not shutil.which('docker') or not shutil.which('uv') or not os.getenv('SANDBOX_IMAGE'), reason='Requires the CI sandbox and trusted uv')
@pytest.mark.parametrize('python_minor', ['3.11', '3.12'])
def test_real_uv_resolver_works_in_the_isolated_production_image(tmp_path, python_minor):
    (tmp_path / 'pyproject.toml').write_text(MANIFEST.replace('>=3.12', '>=' + python_minor))
    (tmp_path / 'uv.lock').write_text(LOCK.replace('>=3.12', '>=' + python_minor))
    (tmp_path / '.python-version').write_text(python_minor)
    result = synchronize_uv_lock(str(tmp_path), 'pyproject.toml')
    assert result['applied']
    assert any(package['name'] == 'idna' for package in validate_lock((tmp_path / 'uv.lock').read_text())['package'])
