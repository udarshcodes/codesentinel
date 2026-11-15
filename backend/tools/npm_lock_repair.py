"""Regenerate a changed npm manifest's lock in a source-free, script-free container."""
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import uuid

from tools.node_dependencies import locked_manifests
from tools.safe_path import resolve_safe_path
from tools.patch_applier import apply_patch


def synchronize_npm_lock(repo, manifest_path):
    relative = PurePosixPath(manifest_path.replace("\\", "/"))
    if relative.name != "package.json":
        return None
    project = os.path.dirname(resolve_safe_path(repo, str(relative)))
    manifest, original = locked_manifests(project, require_sync=False)
    pkg, lock = json.loads(manifest), json.loads(original)
    if all(pkg.get(group, {}) == lock["packages"][""].get(group, {})
           for group in ("dependencies", "devDependencies", "optionalDependencies")):
        return None
    if len(original.encode()) > 512 * 1024:
        raise ValueError("Lockfile exceeds the automatic repair size limit (512 KiB).")
    image = os.getenv("SANDBOX_IMAGE", "ghcr.io/udarshcodes/codesentinel-sandbox:latest")
    if os.getenv("ENVIRONMENT") == "production" and "@sha256:" not in image:
        raise ValueError("Lock regeneration requires an immutable production image.")
    with tempfile.TemporaryDirectory(prefix="codesentinel_lock_") as temporary:
        workspace = Path(temporary)
        (workspace / "package.json").write_text(manifest, encoding="utf-8")
        (workspace / "package-lock.json").write_text(original, encoding="utf-8")
        container = "codesentinel-lock-" + uuid.uuid4().hex
        user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "1000:1000"
        cmd = ["docker", "run", "--rm", "--name", container, "--read-only", "--cap-drop=ALL",
               "--security-opt=no-new-privileges", "--memory=2g", "--pids-limit=128", "--user", user,
               "--tmpfs", "/tmp:size=512m", "--network", "bridge", "-e", "HOME=/tmp",
               "-v", f"{workspace}:/deps", "-w", "/deps", image, "npm", "install", "--package-lock-only",
               "--ignore-scripts", "--no-audit", "--no-fund", "--registry=https://registry.npmjs.org", "--cache=/tmp/npm"]
        environment = {k: v for k, v in os.environ.items() if k.upper() in
                       {"PATH", "HOME", "USERPROFILE", "DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT", "SYSTEMROOT", "TEMP", "TMP"}}
        try:
            result = subprocess.run(cmd, cwd=workspace, env=environment, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=180)
        finally:
            subprocess.run(["docker", "rm", "-f", container], env=environment, capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError("npm lock regeneration failed: " + (result.stdout + result.stderr)[-4000:])
        generated_manifest, generated = locked_manifests(str(workspace))
        if json.loads(generated_manifest) != pkg:
            raise ValueError("npm unexpectedly changed the manifest during lock regeneration.")
        if len(generated.encode()) > 512 * 1024 or "<<<" in original or "<<<" in generated:
            raise ValueError("Generated lock cannot be safely represented in the repair journal.")
        if json.loads(original) == json.loads(generated):
            return None
    target = str(relative.parent / "package-lock.json")
    patch_text = "<<<SEARCH>>>\n" + original.strip("\n") + "\n<<<REPLACE>>>\n" + generated.strip("\n") + "\n"
    result = apply_patch(patch_text, repo, target)
    if not result["success"]:
        raise RuntimeError("Cannot journal generated lock: " + result["stderr"])
    return {"patch_id": "lockfile:" + target, "file": target, "applied": True, "patch_text": patch_text,
            "diff": "".join(difflib.unified_diff(original.splitlines(True), generated.splitlines(True),
                                                fromfile=target, tofile=target)), "generated_by": "npm"}
