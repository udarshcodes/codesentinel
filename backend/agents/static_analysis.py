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
                text=True,
                timeout=120
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for hit in data.get("results", []):
                    findings.append({
                        "file": hit.get("path", ""),
                        "issue": hit.get("extra", {}).get("message", "Semgrep issue"),
                        "rule": hit.get("check_id", ""),
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
                text=True,
                timeout=120
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for hit in data.get("results", []):
                    file_path = hit.get("filename", "")
                    if os.path.isabs(file_path):
                        try:
                            file_path = os.path.relpath(file_path, repo_local_path)
                        except ValueError:
                            pass
                    if file_path.startswith("./") or file_path.startswith(".\\"):
                        file_path = file_path[2:]
                        
                    findings.append({
                        "file": file_path,
                        "issue": hit.get("issue_text", "Bandit issue"),
                        "rule": hit.get("test_id", ""),
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
            text=True,
            timeout=120
        )
        if result.stdout:
            data = json.loads(result.stdout)
            for file_result in data:
                file_path = file_result.get("filePath", "")
                if os.path.isabs(file_path):
                    try:
                        file_path = os.path.relpath(file_path, repo_local_path)
                    except ValueError:
                        pass
                if file_path.startswith("./") or file_path.startswith(".\\"):
                    file_path = file_path[2:]
                
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
                text=True,
                timeout=120
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
                text=True,
                timeout=120
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

    # 6. SonarQube
    sonar_path = shutil.which("sonar-scanner")
    if sonar_path:
        try:
            result = subprocess.run(
                [sonar_path],
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            # Attempt to parse the SonarQube issues report if available
            issues_report = os.path.join(repo_local_path, ".scannerwork", "scanner-report", "issues-report.json")
            if os.path.exists(issues_report) and result.returncode == 0:
                try:
                    with open(issues_report, "r") as f:
                        sonar_data = json.loads(f.read())
                    for issue in sonar_data if isinstance(sonar_data, list) else sonar_data.get("issues", []):
                        findings.append({
                            "file": issue.get("component", "").split(":")[-1] if ":" in issue.get("component", "") else issue.get("component", ""),
                            "issue": issue.get("message", "SonarQube issue"),
                            "rule": issue.get("rule", ""),
                            "tool": "sonarqube",
                            "severity": issue.get("severity", "MEDIUM"),
                            "line": issue.get("line", 1),
                            "category": "quality"
                        })
                except Exception as parse_err:
                    print(f"[StaticAnalysis] SonarQube report parse error: {parse_err}")
            elif result.returncode == 0:
                print("[StaticAnalysis] SonarQube analysis completed but no local report found.")
        except Exception as e:
            print(f"SonarQube execution skipped or failed: {e}")
    else:
        print("[StaticAnalysis] sonar-scanner not found in PATH, skipping.")

    # 7. Performance AST Checker (SQLAlchemy / ORM N+1)
    import ast
    # ORM-related attribute patterns that suggest lazy-loaded relationships
    _ORM_ATTR_HINTS = {'query', 'all', 'filter', 'get', 'first', 'one', 'items', 'values',
                       'children', 'parent', 'relationship', 'related', 'objects', 'select'}
    for root, _, files in os.walk(repo_local_path):
        if "venv" in root or ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    tree = ast.parse(source, filename=file)
                    
                    # Quick check: skip files with no ORM indicators
                    has_orm_indicators = any(kw in source for kw in [
                        'SQLAlchemy', 'session', 'db.', 'Model', 'Base.', 'relationship',
                        'Column(', 'ForeignKey', 'backref', 'orm'
                    ])
                    if not has_orm_indicators:
                        continue
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.For):
                            loop_vars = []
                            for target_node in ast.walk(node.target):
                                if isinstance(target_node, ast.Name):
                                    loop_vars.append(target_node.id)

                            for child in ast.walk(node):
                                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                                    if child.value.id in loop_vars and child.attr.lower() in _ORM_ATTR_HINTS:
                                        rel_path = os.path.relpath(file_path, repo_local_path)
                                        findings.append({
                                            "file": rel_path,
                                            "issue": f"Potential N+1 query: Accessing '{child.attr}' on '{child.value.id}' inside a loop. Consider using joinedload or selectinload.",
                                            "tool": "ast_perf_checker",
                                            "severity": "HIGH",
                                            "line": child.lineno,
                                            "category": "performance"
                                        })
                except Exception as e:
                    print(f"Error parsing {file_path} for AST perf check: {e}")

    # 7. JS/TS Performance Checker (Prisma / Mongoose N+1)
    import re
    loop_pattern = re.compile(r'\b(for|while)\s*\(|\.forEach\s*\(')
    db_query_pattern = re.compile(r'await\s+[a-zA-Z0-9_.]+\.(findMany|findUnique|findOne|find|query)\s*\(')
    
    for root, _, files in os.walk(repo_local_path):
        if "node_modules" in root or ".git" in root or "dist" in root or "build" in root:
            continue
        for file in files:
            if file.endswith((".js", ".ts", ".jsx", ".tsx")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    in_loop = False
                    loop_indent = 0
                    
                    for i, line in enumerate(lines):
                        if loop_pattern.search(line):
                            in_loop = True
                            loop_indent = len(line) - len(line.lstrip())
                        elif in_loop and "}" in line and len(line) - len(line.lstrip()) <= loop_indent:
                            in_loop = False
                        
                        if in_loop and db_query_pattern.search(line):
                            rel_path = os.path.relpath(file_path, repo_local_path)
                            findings.append({
                                "file": rel_path,
                                "issue": f"Potential N+1 query (JS/TS): DB query inside a loop. Consider using Promise.all() or aggregate.",
                                "tool": "js_perf_checker",
                                "severity": "HIGH",
                                "line": i + 1,
                                "category": "performance"
                            })
                except Exception as e:
                    print(f"Error parsing {file_path} for JS perf check: {e}")

    # Deduplicate findings by file and line
    deduped_findings = []
    seen = set()
    for f in findings:
        key = f"{f['file']}:{f['line']}:{f['tool']}"
        if key not in seen:
            seen.add(key)
            deduped_findings.append(f)

    return {"static_findings": deduped_findings}