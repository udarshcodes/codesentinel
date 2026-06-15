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
                        "line": hit.get("start", {}).get("line", 1),
                        "category": "security"
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
                        "line": hit.get("line_number", 1),
                        "category": "security"
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
                        "line": msg.get("line", 1),
                        "category": "quality"
                    })
    except Exception as e:
        print(f"ESLint execution skipped or failed: {e}")

    # 4. Pylint
    pylint_path = shutil.which("pylint")
    if pylint_path:
        try:
            result = subprocess.run(
                [pylint_path, '--disable=all', '--enable=W0611,W0612,R0801,R0401,R0915', '-f', 'json', '.'],
                cwd=repo_local_path,
                capture_output=True,
                text=True
            )
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    for hit in data:
                        file_path = hit.get("path", "")
                        findings.append({
                            "file": file_path,
                            "issue": hit.get("message", "Pylint issue"),
                            "tool": "pylint",
                            "severity": "MEDIUM",
                            "line": hit.get("line", 1),
                            "category": "quality"
                        })
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"Pylint execution skipped or failed: {e}")
    else:
        print("[StaticAnalysis] pylint not found in PATH, skipping.")

    # 5. Flake8
    flake8_path = shutil.which("flake8")
    if flake8_path:
        try:
            result = subprocess.run(
                [flake8_path, '.'],
                cwd=repo_local_path,
                capture_output=True,
                text=True
            )
            if result.stdout:
                for line in result.stdout.splitlines():
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        findings.append({
                            "file": parts[0],
                            "issue": parts[3].strip(),
                            "tool": "flake8",
                            "severity": "LOW",
                            "line": parts[1],
                            "category": "quality"
                        })
        except Exception as e:
            print(f"Flake8 execution skipped or failed: {e}")
    else:
        print("[StaticAnalysis] flake8 not found in PATH, skipping.")

    # 6. Performance AST Checker (SQLAlchemy N+1)
    import ast
    for root, _, files in os.walk(repo_local_path):
        if "venv" in root or ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=file)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.For):
                            # Check for attribute access inside the loop (potential lazy load)
                            for child in ast.walk(node):
                                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                                    if child.value.id == node.target.id if isinstance(node.target, ast.Name) else "":
                                        rel_path = os.path.relpath(file_path, repo_local_path)
                                        findings.append({
                                            "file": rel_path,
                                            "issue": f"Potential N+1 query: Accessing '{child.attr}' on '{child.value.id}' inside a loop. Consider using joinedload or selectinload.",
                                            "tool": "ast_perf_checker",
                                            "severity": "HIGH",
                                            "line": child.lineno,
                                            "category": "performance"
                                        })
                except Exception:
                    pass

    # Deduplicate findings by file and line
    deduped_findings = []
    seen = set()
    for f in findings:
        key = f"{f['file']}:{f['line']}:{f['tool']}"
        if key not in seen:
            seen.add(key)
            deduped_findings.append(f)

    return {"static_findings": deduped_findings}