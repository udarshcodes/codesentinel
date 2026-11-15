"""Resolve locked registry dependencies without giving online npm repository code or secrets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
from urllib.parse import urlsplit

from tools.safe_repo import safe_read_text

_prepared = {}


def locked_manifests(repo, require_sync=True):
    manifest = safe_read_text(repo, "package.json")
    lock = safe_read_text(repo, "package-lock.json")
    pkg, locked = json.loads(manifest), json.loads(lock)
    if pkg.get("overrides"):
        raise ValueError("npm overrides require an operator-prepared image.")
    if pkg.get("workspaces") or locked.get("lockfileVersion") not in (2, 3):
        raise ValueError("Node preparation requires a standalone npm lockfile v2/v3; workspaces need a prepared image.")
    packages = locked.get("packages", {})
    if not packages or len(packages) > 10000:
        raise ValueError("Missing or oversized npm lockfile packages.")
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        for version in pkg.get(group, {}).values():
            if not isinstance(version, str) or any(token in version for token in (":", "/", "\\", "@")):
                raise ValueError("Only ordinary registry version specifications are supported.")
        if require_sync and pkg.get(group, {}) != packages.get("", {}).get(group, {}):
            raise ValueError("package.json and package-lock.json are out of sync; regenerate and review the lockfile.")
    for name, item in packages.items():
        if not name:
            continue
        url = urlsplit(item.get("resolved", ""))
        if item.get("link") or url.scheme != "https" or url.hostname != "registry.npmjs.org" or url.username or url.password or url.port not in (None, 443):
            raise ValueError("Only HTTPS registry.npmjs.org packages are permitted; local/VCS/custom registries need a prepared image.")
        if not item.get("integrity"):
            raise ValueError("Every downloaded npm package must have lockfile integrity metadata.")
    return manifest, lock


def prepare_node_dependencies(repo):
    try:
        manifest, lock = locked_manifests(repo)
        image = os.getenv("SANDBOX_IMAGE", "ghcr.io/udarshcodes/codesentinel-sandbox:latest")
        if os.getenv("ENVIRONMENT") == "production" and "@sha256:" not in image:
            raise ValueError("Node preparation requires an immutable production image.")
        key = (os.path.realpath(repo), image, hashlib.sha256((manifest + lock).encode()).hexdigest())
        if key in _prepared:
            from tools.sandbox_runner import register_node_dependencies
            register_node_dependencies(repo, str(Path(_prepared[key].name) / "node_modules"))
            return {"status": "ready"}
        temporary = tempfile.TemporaryDirectory(prefix="codesentinel_node_")
        workspace = Path(temporary.name)
        (workspace / "package.json").write_text(manifest, encoding="utf-8")
        (workspace / "package-lock.json").write_text(lock, encoding="utf-8")
        user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "1000:1000"
        container = "codesentinel-node-" + uuid.uuid4().hex
        cmd = ["docker", "run", "--rm", "--name", container, "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
               "--memory=2g", "--pids-limit=128", "--user", user, "--tmpfs", "/tmp:size=512m",
               "--network", "bridge", "-e", "HOME=/tmp", "-v", f"{workspace}:/deps", "-w", "/deps", image,
               "npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--registry=https://registry.npmjs.org",
               "--cache=/deps/.npm-cache"]
        environment = {k: v for k, v in os.environ.items() if k.upper() in
                       {"PATH", "HOME", "USERPROFILE", "DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT", "SYSTEMROOT", "TEMP", "TMP"}}
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=180, env=environment, cwd=workspace)
        finally:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=15, env=environment)
        if result.returncode:
            logs = sorted((workspace / ".npm-cache/_logs").glob("*.log"))
            diagnostic = logs[-1].read_text(encoding="utf-8", errors="replace")[-4000:] if logs else ""
            raise RuntimeError("Locked npm preparation failed: " + result.stdout[-1000:] + result.stderr[-1000:] + diagnostic)
        modules = workspace / "node_modules"
        modules.mkdir(exist_ok=True)
        for cache in (".vite-temp", ".vite"):
            (modules / cache).mkdir(exist_ok=True)
        # Linux npm executable links cannot always be stat'ed by a Windows host.
        # Inspect size in an offline container instead of traversing them on host.
        size_cmd = cmd[:cmd.index("npm")] + ["du", "-sm", "/deps/node_modules"]
        size_cmd[size_cmd.index("bridge")] = "none"
        try:
            size = subprocess.run(size_cmd, capture_output=True, text=True, timeout=30, env=environment)
        finally:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=15, env=environment)
        if size.returncode:
            raise RuntimeError("Cannot inspect prepared Node dependency size.")
        if int(size.stdout.split()[0]) > 2048:
            raise ValueError("Prepared Node dependencies exceed 2 GiB.")
        from tools.sandbox_runner import register_node_dependencies
        register_node_dependencies(repo, str(modules))
        _prepared[key] = temporary
        return {"status": "ready"}
    except Exception as error:
        return {"status": "failed", "error": f"{type(error).__name__}: {error}"}
