"""Run each configured project's own ESLint and translate container paths."""
import json
import os
import posixpath
from tools.safe_repo import safe_path_exists, safe_read_text


def scanner_path(path, repo, project=""):
    path = path.replace("\\", "/")
    if path.startswith("/sandbox/repo/"):
        path = posixpath.join(project, path[len("/sandbox/repo/"):])
    elif os.path.isabs(path):
        path = os.path.relpath(path, repo).replace("\\", "/")
    else:
        path = posixpath.join(project, path)
    path = posixpath.normpath(path)
    if path == ".." or path.startswith("../") or path.startswith("/") or ":" in path:
        raise ValueError("Scanner reported a path outside the repository.")
    return path


def scan_eslint_projects(repo, runner):
    findings, notes, failed = [], [], False
    for relative in ("", "frontend", "backend"):
        project = os.path.join(repo, relative)
        pkg = {}
        if safe_path_exists(repo, posixpath.join(relative, "package.json")):
            try:
                pkg = json.loads(safe_read_text(repo, posixpath.join(relative, "package.json")))
            except (ValueError, OSError) as error:
                notes.append(f"ESLint manifest could not be read: {error}")
                failed = True
                continue
        configured = any(safe_path_exists(repo, posixpath.join(relative, name)) for name in
                         ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs")) or pkg.get("eslintConfig")
        if not configured:
            continue
        try:
            has_local = "eslint" in {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if has_local:
                from tools.node_dependencies import prepare_node_dependencies
                prepared = prepare_node_dependencies(project)
                if prepared["status"] != "ready":
                    raise RuntimeError(prepared.get("error", "Dependency preparation unavailable"))
            command = ["node", "node_modules/eslint/bin/eslint.js"] if has_local else ["eslint"]
            result = runner(command + [".", "--format", "json"], cwd=project, timeout=120)
            if result.get("returncode", 0) not in (0, 1) or result.get("status") in ("ERROR", "TIMEOUT", "UNAVAILABLE"):
                raise RuntimeError(result.get("stderr", "ESLint failed"))
            data = json.loads(result.get("stdout", ""))
            if not isinstance(data, list):
                raise ValueError("ESLint returned an invalid report.")
            for file in data:
                for msg in file.get("messages", []):
                    if msg.get("fatal"):
                        failed = True
                    findings.append({"file": scanner_path(file.get("filePath", ""), repo, relative),
                                     "issue": msg.get("message", "ESLint issue"), "rule": msg.get("ruleId"), "tool": "eslint",
                                     "severity": "HIGH" if msg.get("severity") == 2 else "MEDIUM",
                                     "line": msg.get("line", 1), "category": "quality"})
        except Exception as error:
            failed = True
            notes.append(f"ESLint in {relative or '.'} was unavailable: {error}")
    if not findings and not failed:
        notes.append("ESLint uses explicit project configuration; unconfigured projects are not treated as lint-verified.")
    return findings, notes, failed
