import subprocess
import json


def run_semgrep_on_files(files: list[str]) -> list:
    """Run semgrep scoped to specific files only — used by Security Verifier"""
    if not files:
        return []
    try:
        result = subprocess.run(
            ["semgrep", "--config=auto", "--json"] + files,
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(result.stdout or "{}")
        return data.get("results", [])
    except Exception as e:
        print(f"[AnalysisRunner] Semgrep failed: {e}")
        return []


def run_bandit_on_files(files: list[str]) -> list:
    """Run bandit scoped to specific files only"""
    if not files:
        return []
    try:
        result = subprocess.run(
            ["bandit", "-f", "json"] + files, capture_output=True, text=True, timeout=30
        )
        data = json.loads(result.stdout or "{}")
        return data.get("results", [])
    except Exception as e:
        print(f"[AnalysisRunner] Bandit failed: {e}")
        return []
