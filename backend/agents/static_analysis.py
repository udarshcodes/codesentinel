import os
import json
import shutil
import subprocess
import ast
import re
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
                timeout=120,
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for hit in data.get("results", []):
                    findings.append(
                        {
                            "file": hit.get("path", ""),
                            "issue": hit.get("extra", {}).get(
                                "message", "Semgrep issue"
                            ),
                            "rule": hit.get("check_id", ""),
                            "tool": "semgrep",
                            "severity": hit.get("extra", {}).get("severity", "WARNING"),
                            "line": hit.get("start", {}).get("line", 1),
                            "category": "security",
                        }
                    )
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
                timeout=120,
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

                    findings.append(
                        {
                            "file": file_path,
                            "issue": hit.get("issue_text", "Bandit issue"),
                            "rule": hit.get("test_id", ""),
                            "tool": "bandit",
                            "severity": hit.get("issue_severity", "MEDIUM"),
                            "line": hit.get("line_number", 1),
                            "category": "security",
                        }
                    )
        except Exception as e:
            print(f"Bandit execution skipped or failed: {e}")
    else:
        print("[StaticAnalysis] bandit not found in PATH, skipping.")

    # 3. ESLint
    try:
        # ESLint might return non-zero exit code if it finds errors, but it still prints json to stdout
        result = subprocess.run(
            ["npx", "--yes", "eslint", ".", "--format", "json"],
            cwd=repo_local_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            try:
                start_idx = result.stdout.find("[")
                json_str = (
                    result.stdout[start_idx:] if start_idx != -1 else result.stdout
                )
                data = json.loads(json_str)
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
                        findings.append(
                            {
                                "file": file_path,
                                "issue": msg.get("message", "ESLint issue"),
                                "tool": "eslint",
                                "severity": (
                                    "HIGH" if msg.get("severity") == 2 else "MEDIUM"
                                ),
                                "line": msg.get("line", 1),
                                "category": "quality",
                            }
                        )
            except Exception:
                pass
    except Exception as e:
        print(f"ESLint execution skipped or failed: {e}")

    # 4. Pylint
    pylint_path = shutil.which("pylint")
    if pylint_path:
        try:
            result = subprocess.run(
                [
                    pylint_path,
                    "--disable=all",
                    "--enable=W0611,W0612,R0801,R0401,R0915",
                    "-f",
                    "json",
                    ".",
                ],
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.stdout:
                try:
                    start_idx = result.stdout.find("[")
                    json_str = (
                        result.stdout[start_idx:] if start_idx != -1 else result.stdout
                    )
                    data = json.loads(json_str)
                    for hit in data:
                        file_path = hit.get("path", "")
                        findings.append(
                            {
                                "file": file_path,
                                "issue": hit.get("message", "Pylint issue"),
                                "tool": "pylint",
                                "severity": "MEDIUM",
                                "line": hit.get("line", 1),
                                "category": "quality",
                            }
                        )
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
                [flake8_path, "."],
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.stdout:
                for line in result.stdout.splitlines():
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        findings.append(
                            {
                                "file": parts[0],
                                "issue": parts[3].strip(),
                                "tool": "flake8",
                                "severity": "LOW",
                                "line": int(parts[1]),
                                "category": "quality",
                            }
                        )
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
                timeout=300,
            )
            # Attempt to parse the SonarQube issues report if available
            issues_report = os.path.join(
                repo_local_path, ".scannerwork", "scanner-report", "issues-report.json"
            )
            if os.path.exists(issues_report) and result.returncode == 0:
                try:
                    with open(issues_report, "r") as f:
                        sonar_data = json.loads(f.read())
                    for issue in (
                        sonar_data
                        if isinstance(sonar_data, list)
                        else sonar_data.get("issues", [])
                    ):
                        findings.append(
                            {
                                "file": (
                                    issue.get("component", "").split(":")[-1]
                                    if ":" in issue.get("component", "")
                                    else issue.get("component", "")
                                ),
                                "issue": issue.get("message", "SonarQube issue"),
                                "rule": issue.get("rule", ""),
                                "tool": "sonarqube",
                                "severity": issue.get("severity", "MEDIUM"),
                                "line": issue.get("line", 1),
                                "category": "quality",
                            }
                        )
                except Exception as parse_err:
                    print(f"[StaticAnalysis] SonarQube report parse error: {parse_err}")
            elif result.returncode == 0:
                print(
                    "[StaticAnalysis] SonarQube analysis completed but no local report found."
                )
        except Exception as e:
            print(f"SonarQube execution skipped or failed: {e}")
    else:
        print("[StaticAnalysis] sonar-scanner not found in PATH, skipping.")

    # 7. Performance AST Checker (SQLAlchemy / ORM N+1)
    import ast

    # ORM-related attribute patterns that suggest lazy-loaded relationships
    _ORM_ATTR_HINTS = {
        "query",
        "all",
        "filter",
        "get",
        "first",
        "one",
        "items",
        "values",
        "children",
        "parent",
        "relationship",
        "related",
        "objects",
        "select",
    }
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
                    has_orm_indicators = any(
                        kw in source
                        for kw in [
                            "SQLAlchemy",
                            "session",
                            "db.",
                            "Model",
                            "Base.",
                            "relationship",
                            "Column(",
                            "ForeignKey",
                            "backref",
                            "orm",
                        ]
                    )
                    if not has_orm_indicators:
                        continue

                    for node in ast.walk(tree):
                        if isinstance(node, ast.For):
                            loop_vars = []
                            for target_node in ast.walk(node.target):
                                if isinstance(target_node, ast.Name):
                                    loop_vars.append(target_node.id)

                            for child in ast.walk(node):
                                if isinstance(child, ast.Attribute) and isinstance(
                                    child.value, ast.Name
                                ):
                                    if (
                                        child.value.id in loop_vars
                                        and child.attr.lower() in _ORM_ATTR_HINTS
                                    ):
                                        rel_path = os.path.relpath(
                                            file_path, repo_local_path
                                        )
                                        findings.append(
                                            {
                                                "file": rel_path,
                                                "issue": f"Potential N+1 query: Accessing '{child.attr}' on '{child.value.id}' inside a loop. Consider using joinedload or selectinload.",
                                                "tool": "ast_perf_checker",
                                                "severity": "HIGH",
                                                "line": child.lineno,
                                                "category": "performance",
                                            }
                                        )
                except Exception as e:
                    print(f"Error parsing {file_path} for AST perf check: {e}")

    # 8. JS/TS Performance Checker (Prisma / Mongoose N+1)
    import re

    loop_pattern = re.compile(r"\b(for|while)\s*\(|\.forEach\s*\(")
    db_query_pattern = re.compile(
        r"await\s+[a-zA-Z0-9_.]+\.(findMany|findUnique|findOne|find|query)\s*\("
    )

    for root, _, files in os.walk(repo_local_path):
        if (
            "node_modules" in root
            or ".git" in root
            or "dist" in root
            or "build" in root
        ):
            continue
        for file in files:
            if file.endswith((".js", ".ts", ".jsx", ".tsx")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    in_loop = False
                    brace_count = 0

                    for i, line in enumerate(lines):
                        if not in_loop and loop_pattern.search(line):
                            in_loop = True
                            brace_count = line.count("{") - line.count("}")
                        elif in_loop:
                            brace_count += line.count("{") - line.count("}")
                            if brace_count <= 0 and "}" in line:
                                in_loop = False

                        if in_loop and db_query_pattern.search(line):
                            rel_path = os.path.relpath(file_path, repo_local_path)
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": "Potential N+1 query (JS/TS): DB query inside a loop. Consider using Promise.all() or aggregate.",
                                    "tool": "js_perf_checker",
                                    "severity": "HIGH",
                                    "line": i + 1,
                                    "category": "performance",
                                }
                            )
                except Exception as e:
                    print(f"Error parsing {file_path} for JS perf check: {e}")

    # 9. Memory Leak Detection — Python (open() without 'with')
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
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            # Look for: var = open(...)  (not inside a with block)
                            if isinstance(node.value, ast.Call):
                                func = node.value.func
                                func_name = ""
                                if isinstance(func, ast.Name):
                                    func_name = func.id
                                elif isinstance(func, ast.Attribute):
                                    func_name = func.attr
                                if func_name == "open":
                                    # Check if this assignment is inside a with statement
                                    is_in_with = _is_inside_with(tree, node.lineno)
                                    if not is_in_with:
                                        rel_path = os.path.relpath(
                                            file_path, repo_local_path
                                        )
                                        findings.append(
                                            {
                                                "file": rel_path,
                                                "issue": f"Potential memory leak: file opened with open() without a 'with' statement (line {node.lineno}). Use 'with open(...) as f:' to ensure the file handle is closed.",
                                                "tool": "memory_leak_checker",
                                                "severity": "MEDIUM",
                                                "line": node.lineno,
                                                "category": "performance",
                                            }
                                        )
                except Exception:
                    pass

    # 10. Memory Leak Detection — JS/TS (addEventListener without removeEventListener,
    #     setInterval without clearInterval)
    _LEAK_PAIRS = [
        ("addEventListener", "removeEventListener"),
        ("setInterval", "clearInterval"),
        ("setTimeout", "clearTimeout"),
        (".on(", ".off("),
    ]
    for root, _, files in os.walk(repo_local_path):
        if "node_modules" in root or ".git" in root or "dist" in root:
            continue
        for file in files:
            if file.endswith((".js", ".ts", ".jsx", ".tsx")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    for add_call, remove_call in _LEAK_PAIRS:
                        if add_call in content and remove_call not in content:
                            # Find the line number of the first occurrence
                            for i, line in enumerate(content.splitlines()):
                                if add_call in line:
                                    rel_path = os.path.relpath(
                                        file_path, repo_local_path
                                    )
                                    findings.append(
                                        {
                                            "file": rel_path,
                                            "issue": f"Potential memory leak: '{add_call}' found without matching '{remove_call}'. This can cause memory leaks if listeners/timers are not cleaned up.",
                                            "tool": "memory_leak_checker",
                                            "severity": "MEDIUM",
                                            "line": i + 1,
                                            "category": "performance",
                                        }
                                    )
                                    break  # One finding per pair per file
                except Exception:
                    pass

    # 11. Circular Dependency Detection (using knowledge graph)
    try:
        from tools.knowledge_graph import build_knowledge_graph

        kg = build_knowledge_graph(repo_local_path)
        cycles = kg.find_cycles()
        for cycle in cycles:
            cycle_str = " → ".join(cycle)
            findings.append(
                {
                    "file": cycle[0],
                    "issue": f"Circular dependency detected: {cycle_str}. Circular imports can cause ImportError at runtime and indicate tight coupling.",
                    "tool": "circular_dep_checker",
                    "severity": "HIGH",
                    "line": 1,
                    "category": "quality",
                }
            )
    except Exception as e:
        print(f"[StaticAnalysis] Circular dependency check failed: {e}")

    # 12. Duplicate Code Detection (function body hashing)
    import hashlib

    function_hashes: dict[str, list[tuple[str, str, int]]] = (
        {}
    )  # hash -> [(file, name, line)]

    for root, _, files in os.walk(repo_local_path):
        if any(
            skip in root
            for skip in [".git", "node_modules", "venv", "__pycache__", "dist"]
        ):
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    tree = ast.parse(source, filename=file)
                    lines = source.splitlines()
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if (
                                not hasattr(node, "end_lineno")
                                or node.end_lineno is None
                            ):
                                continue
                            body_lines = lines[
                                node.lineno : node.end_lineno
                            ]  # Skip signature
                            if len(body_lines) < 5:
                                continue  # Skip trivial functions
                            normalized = "\n".join(
                                line.strip() for line in body_lines if line.strip()
                            )
                            h = hashlib.md5(normalized.encode()).hexdigest()
                            rel_path = os.path.relpath(file_path, repo_local_path)
                            if h not in function_hashes:
                                function_hashes[h] = []
                            function_hashes[h].append(
                                (rel_path, node.name, node.lineno)
                            )
                except Exception:
                    pass
            elif file.endswith((".js", ".ts", ".jsx", ".tsx")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    _extract_and_hash_js_functions(
                        content, file_path, repo_local_path, function_hashes
                    )
                except Exception:
                    pass

    for h, locations in function_hashes.items():
        if len(locations) >= 2:
            files_str = ", ".join(f"{loc[0]}:{loc[1]}(L{loc[2]})" for loc in locations)
            for loc in locations:
                findings.append(
                    {
                        "file": loc[0],
                        "issue": f"Duplicate code: Function '{loc[1]}' has an identical body to functions in: {files_str}. Consider extracting to a shared utility.",
                        "tool": "duplicate_code_checker",
                        "severity": "MEDIUM",
                        "line": loc[2],
                        "category": "quality",
                    }
                )

    # Deduplicate findings by file and line
    deduped_findings = []
    seen = set()
    for f in findings:
        key = f"{f['file']}:{f['line']}:{f['tool']}"
        if key not in seen:
            seen.add(key)
            deduped_findings.append(f)

    return {"static_findings": deduped_findings}


def _is_inside_with(tree, target_lineno: int) -> bool:
    """Check if a given line number is inside a 'with' statement in the AST."""
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            if hasattr(node, "end_lineno") and node.end_lineno is not None:
                if node.lineno <= target_lineno <= node.end_lineno:
                    return True
    return False


def _extract_and_hash_js_functions(
    content: str, file_path: str, repo_local_path: str, function_hashes: dict
):
    """Extract JS/TS function bodies using regex and add their hashes."""
    import hashlib

    lines = content.splitlines()
    func_pattern = re.compile(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)|"
        r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?"
    )
    i = 0
    while i < len(lines):
        m = func_pattern.match(lines[i].strip())
        if m and "{" in lines[i]:
            name = m.group(1) or m.group(2) or f"anon_L{i + 1}"
            start = i
            brace_depth = 0
            for j in range(i, len(lines)):
                brace_depth += lines[j].count("{") - lines[j].count("}")
                if brace_depth <= 0 and j > i:
                    body_lines = lines[start + 1 : j]
                    if len(body_lines) >= 5:
                        normalized = "\n".join(
                            line.strip() for line in body_lines if line.strip()
                        )
                        h = hashlib.md5(normalized.encode()).hexdigest()
                        rel_path = os.path.relpath(file_path, repo_local_path)
                        if h not in function_hashes:
                            function_hashes[h] = []
                        function_hashes[h].append((rel_path, name, start + 1))
                    i = j + 1
                    break
            else:
                i += 1
        else:
            i += 1
