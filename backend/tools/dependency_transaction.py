"""Restore unresolved dependency transactions without discarding independent repairs."""
from pathlib import PurePosixPath

from tools.safe_path import open_safe
from tools.safe_repo import safe_path_exists, safe_read_text

LOCKFILES = {
    "pyproject.toml": ("uv.lock", "poetry.lock"),
    "package.json": ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml"),
    "requirements.txt": (),
    "Cargo.toml": ("Cargo.lock",),
}


def capture_manifest(repo, path, originals):
    """Capture once, before any proposed mutation; never infer originals from patches."""
    manifest = PurePosixPath(path)
    if manifest.name not in LOCKFILES or path in originals:
        return
    paths = [path] + [str(manifest.parent / name) for name in LOCKFILES[manifest.name]]
    snapshot = {}
    for name in paths:
        if safe_path_exists(repo, name):
            content = safe_read_text(repo, name, max_bytes=2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Dependency baseline exceeds safe size limit")
            snapshot[name] = content
    originals[path] = snapshot


def rollback_dependencies(state, manifests, reason):
    originals = state.get("manifest_originals", {})
    restored = set()
    for manifest in sorted(set(manifests)):
        snapshot = originals.get(manifest)
        if not snapshot or manifest not in snapshot:
            raise ValueError("Cannot safely restore dependency manifest without an original baseline")
        for path, content in snapshot.items():
            with open_safe(state["repo_local_path"], path, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
            restored.add(path)
    blocked_ids = set()
    issues = []
    for issue in state.get("investigated_issues", []):
        issue = dict(issue)
        if set(issue.get("affected_files", [])) & set(manifests):
            issue.update(remediation_mode="manual_review", remediation_reason=reason)
            blocked_ids.add(issue.get("id"))
        issues.append(issue)
    patches = []
    for patch in state.get("patches", []):
        patch = dict(patch)
        if patch.get("file") in restored:
            patch.update(applied=False, excluded_from_validation=True, error=reason)
            blocked_ids.add(patch.get("patch_id"))
        patches.append(patch)
    return {
        "patches": patches,
        "investigated_issues": issues,
        "repair_plan": [plan for plan in state.get("repair_plan", []) if plan.get("issue_id") not in blocked_ids],
        "dependency_blocked_files": sorted(set(state.get("dependency_blocked_files", [])) | set(manifests)),
        "pr_error": "",
    }
