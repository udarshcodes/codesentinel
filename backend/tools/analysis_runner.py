import subprocess
import json

def run_semgrep_on_files(files: list[str]) -> list:
    """Run semgrep scoped to specific files only — used by Security Verifier"""
    if not files:
        return []
    try:
        result = subprocess.run(
            ['semgrep', '--config=auto', '--json'] + files,
            capture_output=True, text=True, timeout=60
        )
        data = json.loads(result.stdout or '{}')
        return data.get('results', [])
    except Exception as e:
        print(f"[AnalysisRunner] Semgrep failed: {e}")
        return []

def run_bandit_on_files(files: list[str]) -> list:
    """Run bandit scoped to specific files only"""
    if not files:
        return []
    try:
        result = subprocess.run(
            ['bandit', '-f', 'json'] + files,
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(result.stdout or '{}')
        return data.get('results', [])
    except Exception as e:
        print(f"[AnalysisRunner] Bandit failed: {e}")
        return []

def run_pylint_on_files(files: list[str]) -> list:
    """Run pylint scoped to specific files only"""
    if not files:
        return []
    try:
        # Check for dead code, duplicate code, circular dependencies, long methods
        # pylint --disable=all --enable=W0611,W0612,R0801,R0401,R0915 -f json <files>
        result = subprocess.run(
            ['pylint', '--disable=all', '--enable=W0611,W0612,R0801,R0401,R0915', '-f', 'json'] + files,
            capture_output=True, text=True, timeout=60
        )
        data = json.loads(result.stdout or '[]')
        return data
    except Exception as e:
        print(f"[AnalysisRunner] Pylint failed: {e}")
        return []

def run_flake8_on_files(files: list[str]) -> list:
    """Run flake8 scoped to specific files only"""
    if not files:
        return []
    try:
        # --format=default, we parse lines manually since flake8 doesn't output json natively without a plugin
        result = subprocess.run(
            ['flake8'] + files,
            capture_output=True, text=True, timeout=60
        )
        out = result.stdout or ""
        findings = []
        for line in out.splitlines():
            # format: path:line:col: code msg
            parts = line.split(":", 3)
            if len(parts) >= 4:
                findings.append({
                    "file": parts[0],
                    "line": parts[1],
                    "message": parts[3].strip()
                })
        return findings
    except Exception as e:
        print(f"[AnalysisRunner] Flake8 failed: {e}")
        return []
