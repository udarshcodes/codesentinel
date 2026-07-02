import os
import subprocess
import json


def run_semgrep_on_files(files: list[str], cwd: str = None) -> list:
    """Run semgrep scoped to specific files only — used by Security Verifier"""
    if not files:
        return []
    try:
        result = subprocess.run(
            ["semgrep", "--config=auto", "--json"] + files,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            shell=(os.name == "nt"),
        )
        data = json.loads(result.stdout or "{}")
        return data.get("results", [])
    except Exception as e:
        print(f"[AnalysisRunner] Semgrep failed: {e}")
        return []


def run_bandit_on_files(files: list[str], cwd: str = None) -> list:
    """Run bandit scoped to specific files only"""
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return []
    try:
        result = subprocess.run(
            ["bandit", "-f", "json"] + py_files,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            shell=(os.name == "nt"),
        )
        data = json.loads(result.stdout or "{}")
        return data.get("results", [])
    except Exception as e:
        print(f"[AnalysisRunner] Bandit failed: {e}")
        return []
