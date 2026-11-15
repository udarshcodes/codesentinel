import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tools.node_dependencies import locked_manifests, prepare_node_dependencies


def fixture(repo, url="https://registry.npmjs.org/example/-/example-1.0.0.tgz"):
    (repo / "package.json").write_text(json.dumps({"dependencies": {"example": "1.0.0"}, "scripts": {"preinstall": "exit 91"}}))
    (repo / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {
        "": {"dependencies": {"example": "1.0.0"}},
        "node_modules/example": {"version": "1.0.0", "resolved": url, "integrity": "sha512-example"}}}))


@pytest.mark.parametrize("url", ["file:///secret", "https://evil.example/file.tgz", "git+https://github.com/a/b", "https://user:password@registry.npmjs.org/a"])
def test_rejects_non_registry_downloads(tmp_path, url):
    fixture(tmp_path, url)
    with pytest.raises(ValueError):
        locked_manifests(str(tmp_path))


def test_rejects_stale_lock_before_any_online_execution(tmp_path):
    fixture(tmp_path)
    (tmp_path / "package.json").write_text('{"dependencies":{"example":"2.0.0"}}')
    with patch("tools.node_dependencies.subprocess.run") as run:
        assert prepare_node_dependencies(str(tmp_path))["status"] == "failed"
    run.assert_not_called()


def test_online_container_has_only_manifests_and_disables_scripts(tmp_path):
    fixture(tmp_path)
    def run(cmd, **kwargs):
        if cmd[1] == "run" and "npm" in cmd:
            assert "--ignore-scripts" in cmd
            assert "--no-audit" in cmd
            mounts = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-v"]
            assert len(mounts) == 1 and str(tmp_path) not in mounts[0]
            from pathlib import Path
            workspace = Path(kwargs["cwd"])
            assert {p.name for p in workspace.iterdir()} == {"package.json", "package-lock.json"}
            (workspace / "node_modules").mkdir()
        return SimpleNamespace(returncode=0, stderr="", stdout="1 /deps/node_modules")
    with patch("tools.node_dependencies.subprocess.run", side_effect=run), patch("tools.sandbox_runner.register_node_dependencies") as register:
        assert prepare_node_dependencies(str(tmp_path))["status"] == "ready"
        register.assert_called_once()
