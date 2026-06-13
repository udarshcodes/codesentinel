import os
import json
import shutil
import subprocess
from models.pipeline_state import PipelineState

async def agent_static_analysis(state: PipelineState):
    repo_local_path = state.get("repo_local_path", "")
    findings = []

    if not repo_local_path or not os.path.exists(repo_local_path):
        return {"static_findings": findings}

    # 1. Semgrep
    semgrep_path = shutil.which("semgrep")
    if semgrep_path:
        try:
            result = subprocess.run(
                [semgrep_path, "--config=auto", "--json", "."],
                cwd=repo_local_path,
                capture_output=True,
                text=True
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for hit in data.get("results", []):
                    findings.append({
                        "file": hit.get("path", ""),
                        "issue": hit.get("extra", {}).get("message", "Semgrep issue"),
                        "tool": "semgrep",
                        "severity": hit.get("extra", {}).get("severity", "WARNING"),
                        "line": hit.get("start", {}).get("line", 1)
                    })
        except Exception as e:
            print(f"Semgrep execution skipped or failed: {e}")
    else:
        print("[StaticAnalysis] semgrep not found in PATH, skipping.")

    # 2. Bandit
    bandit_path = shutil.which("bandit")
    if bandit_path:
        try:
            result = subprocess.run(
                [bandit_path, "-r", ".", "-f", "json"],
                cwd=repo_local_path,
                capture_output=True,
                text=True
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for hit in data.get("results", []):
                    file_path = hit.get("filename", "")
                    # Clean up path to be relative
                    file_path = file_path.replace(f"{repo_local_path}/", "").replace(f"{repo_local_path}\\", "")
                    if file_path.startswith("./") or file_path.startswith(".\\"):
                        file_path = file_path[2:]
                        
                    findings.append({
                        "file": file_path,
                        "issue": hit.get("issue_text", "Bandit issue"),
                        "tool": "bandit",
                        "severity": hit.get("issue_severity", "MEDIUM"),
                        "line": hit.get("line_number", 1)
                    })
        except Exception as e:
            print(f"Bandit execution skipped or failed: {e}")
    else:
        print("[StaticAnalysis] bandit not found in PATH, skipping.")

    # 3. ESLint
    try:
        # ESLint might return non-zero exit code if it finds errors, but it still prints json to stdout
        result = subprocess.run(
            ["npx", "eslint", ".", "--format", "json"],
            cwd=repo_local_path,
            capture_output=True,
            text=True
        )
        if result.stdout:
            data = json.loads(result.stdout)
            for file_result in data:
                file_path = file_result.get("filePath", "")
                file_path = file_path.replace(f"{repo_local_path}/", "").replace(f"{repo_local_path}\\", "")
                
                for msg in file_result.get("messages", []):
                    findings.append({
                        "file": file_path,
                        "issue": msg.get("message", "ESLint issue"),
                        "tool": "eslint",
                        "severity": "HIGH" if msg.get("severity") == 2 else "MEDIUM",
                        "line": msg.get("line", 1)
                    })
    except Exception as e:
        print(f"ESLint execution skipped or failed: {e}")

    return {"static_findings": findings}