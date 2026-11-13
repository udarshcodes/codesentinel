"""Prepare wheel-only Python dependencies without executing repository code online."""
import os
import subprocess
import tempfile
from pathlib import Path
from packaging.requirements import Requirement, InvalidRequirement
from tools.safe_repo import safe_path_exists, safe_read_text

_prepared = {}


def python_requirements(repo):
    values = []
    if safe_path_exists(repo, "pyproject.toml"):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        config = tomllib.loads(safe_read_text(repo, "pyproject.toml"))
        values.extend(config.get("project", {}).get("dependencies", []))
        for name, deps in config.get("project", {}).get("optional-dependencies", {}).items():
            if name.lower() in {"test", "tests", "testing"}:
                values.extend(deps)
    if safe_path_exists(repo, "requirements.txt"):
        values.extend(line.split(" #", 1)[0].strip() for line in safe_read_text(repo, "requirements.txt").splitlines()
                      if line.strip() and not line.lstrip().startswith("#"))
    if len(values) > 128:
        raise ValueError("Dependency manifest exceeds the 128-requirement preparation limit.")
    requirements = []
    for value in values:
        try:
            requirement = Requirement(value)
        except (InvalidRequirement, TypeError) as error:
            raise ValueError("Only ordinary PyPI requirements are supported; includes, options and editable installs require a prepared image.") from error
        if requirement.url:
            raise ValueError("Direct URL/VCS dependencies require an operator-prepared sandbox image.")
        requirements.append(str(requirement))
    return sorted(set(requirements))


def prepare_python_dependencies(repo):
    repo = os.path.realpath(repo)
    cache_key = (repo, ())
    try:
        requirements = python_requirements(repo)
        cache_key = (repo, tuple(requirements))
        if cache_key in _prepared:
            return _prepared[cache_key][0]
        if not requirements:
            return {"status": "not_required"}
        image = os.getenv("SANDBOX_IMAGE", "ghcr.io/udarshcodes/codesentinel-sandbox:latest")
        if os.getenv("ENVIRONMENT") == "production" and "@sha256:" not in image:
            raise ValueError("Dependency preparation requires an immutable production image.")
        temporary = tempfile.TemporaryDirectory(prefix="codesentinel_dependencies_")
        workspace = Path(temporary.name)
        manifest = workspace / "requirements.txt"
        manifest.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        wheels = workspace / "wheels"
        packages = workspace / "packages"
        wheels.mkdir()
        packages.mkdir()
        user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "1000:1000"
        prefix = ["docker", "run", "--rm", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                  "--memory=2g", "--pids-limit=128", "--user", user, "--tmpfs", "/tmp:size=512m",
                  "-e", "HOME=/tmp", "-v", f"{manifest}:/requirements.txt:ro", "-v", f"{wheels}:/wheels"]
        environment = {k: v for k, v in os.environ.items() if k.upper() in
                       {"PATH", "HOME", "USERPROFILE", "DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT", "SYSTEMROOT", "TEMP", "TMP"}}
        # An operator-prepared image can satisfy legacy/native requirements already.
        probe_code = "from importlib.metadata import version; from packaging.requirements import Requirement; import sys; rs=[Requirement(s) for s in open('/requirements.txt') if s.strip()]; sys.exit(0 if all((r.marker and not r.marker.evaluate()) or r.specifier.contains(version(r.name), prereleases=True) for r in rs) else 1)"
        probe = subprocess.run(prefix + ["--network", "none", image, "python", "-c", probe_code],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=environment, cwd=workspace)
        if probe.returncode == 0:
            outcome = {"status": "image_ready", "requirements_count": len(requirements)}
            _prepared[cache_key] = (outcome, temporary)
            return outcome
        # This online container has no repository mount or secrets. Wheel metadata is
        # resolved/downloaded only; sdists, VCS URLs and install scripts are forbidden.
        download = prefix + ["--network", "bridge", image, "python", "-m", "pip", "--isolated",
                             "--disable-pip-version-check", "--no-cache-dir", "download", "--only-binary=:all:",
                             "--index-url=https://pypi.org/simple", "--dest=/wheels", "-r", "/requirements.txt"]
        result = subprocess.run(download, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, env=environment, cwd=workspace)
        if result.returncode:
            raise RuntimeError("Wheel resolution/download failed (no source builds are permitted): " + result.stderr[-1600:])
        if sum(p.stat().st_size for p in wheels.iterdir()) > 750 * 1024 * 1024:
            raise RuntimeError("Dependency wheels exceed the 750 MiB preparation limit.")
        install = prefix + ["--network", "none", "-v", f"{packages}:/deps", image, "python", "-m", "pip", "--isolated",
                            "--disable-pip-version-check", "--no-cache-dir", "install", "--no-index", "--find-links=/wheels",
                            "--only-binary=:all:", "--target=/deps", "-r", "/requirements.txt"]
        result = subprocess.run(install, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=environment, cwd=workspace)
        if result.returncode:
            raise RuntimeError("Offline wheel installation failed: " + result.stderr[-1600:])
        from tools.sandbox_runner import register_project_dependencies
        register_project_dependencies(repo, str(packages))
        outcome = {"status": "ready", "requirements_count": len(requirements)}
        _prepared[cache_key] = (outcome, temporary)
        return outcome
    except Exception as error:
        outcome = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
        _prepared[cache_key] = (outcome, None)
        return outcome
