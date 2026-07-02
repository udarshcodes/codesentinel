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
                shell=(os.name == "nt"),
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
                shell=(os.name == "nt"),
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for hit in data.get("results", []):
                    file_path = hit.get("filename", "")
                    if os.path.isabs(file_path):
                        try:
                            file_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
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
            shell=(os.name == "nt"),
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
                            file_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
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
                shell=(os.name == "nt"),
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
                shell=(os.name == "nt"),
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
                shell=(os.name == "nt"),
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

    # 6b. Go Vet
    go_path = shutil.which("go")
    if go_path:
        gomod_paths = []
        for root_dir, dirs, files in os.walk(repo_local_path):
            if "node_modules" in dirs:
                dirs.remove("node_modules")
            if "go.mod" in files:
                gomod_paths.append(root_dir)
        
        for gmdir in gomod_paths:
            try:
                result = subprocess.run(
                    [go_path, "vet", "./..."],
                    cwd=gmdir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    shell=(os.name == "nt"),
                )
                if result.stderr:
                    for line in result.stderr.splitlines():
                        parts = line.split(":", 3)
                        if len(parts) >= 4 and parts[0].endswith(".go"):
                            # parts[0] is relative to gmdir
                            rel_file = os.path.relpath(os.path.join(gmdir, parts[0]), repo_local_path).replace("\\", "/")
                            findings.append(
                                {
                                    "file": rel_file,
                                    "issue": parts[3].strip(),
                                    "tool": "go_vet",
                                    "severity": "MEDIUM",
                                    "line": int(parts[1]) if parts[1].isdigit() else 1,
                                    "category": "quality",
                                }
                            )
            except Exception as e:
                print(f"go vet execution skipped or failed in {gmdir}: {e}")
    else:
        print("[StaticAnalysis] go not found in PATH, skipping go vet.")

    # 6c. Cargo Clippy (Rust static analysis)
    cargo_path = shutil.which("cargo")
    if cargo_path:
        cargo_paths = []
        for root_dir, dirs, files in os.walk(repo_local_path):
            if "node_modules" in dirs:
                dirs.remove("node_modules")
            if "Cargo.toml" in files:
                cargo_paths.append(root_dir)
                
        for cdir in cargo_paths:
            try:
                result = subprocess.run(
                    [
                        cargo_path,
                        "clippy",
                        "--message-format=json",
                        "--",
                        "-W",
                        "clippy::all",
                    ],
                    cwd=cdir,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    shell=(os.name == "nt"),
                )
                if result.stdout:
                    for json_line in result.stdout.splitlines():
                        try:
                            msg = json.loads(json_line)
                            if msg.get("reason") == "compiler-message":
                                cm = msg.get("message", {})
                                spans = cm.get("spans", [])
                                primary = next(
                                    (s for s in spans if s.get("is_primary")),
                                    spans[0] if spans else {},
                                )
                                rel_file = os.path.relpath(os.path.join(cdir, primary.get("file_name", "")), repo_local_path).replace("\\", "/")
                                findings.append(
                                    {
                                        "file": rel_file,
                                        "issue": cm.get("message", "Clippy warning"),
                                        "tool": "cargo_clippy",
                                        "severity": (
                                            "MEDIUM"
                                            if cm.get("level") == "warning"
                                            else "HIGH"
                                        ),
                                        "line": primary.get("line_start", 1),
                                        "category": "quality",
                                    }
                                )
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"Cargo clippy skipped or failed in {cdir}: {e}")
    else:
        if not cargo_path:
            print("[StaticAnalysis] cargo not found in PATH, skipping clippy.")

    # 7. Performance AST Checker (SQLAlchemy / ORM N+1)

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
                                        ).replace("\\", "/")
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
                            rel_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
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
                                        ).replace("\\", "/")
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
                                    ).replace("\\", "/")
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

    # 10b. ReDoS (Regular Expression Denial of Service) Detection
    _REDOS_PATTERNS = [
        re.compile(r"\([^)]*\+\)\+"),
        re.compile(r"\([^)]*\*\)\*"),
        re.compile(r"\([^)]*\+\)\*"),
        re.compile(r"\([^)]*\*\)\+"),
    ]
    for root, _, files in os.walk(repo_local_path):
        if any(
            skip in root
            for skip in [".git", "node_modules", "dist", "build", "venv", "__pycache__"]
        ):
            continue
        for file in files:
            if file.endswith((".js", ".ts", ".jsx", ".tsx", ".py")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    for i, line in enumerate(lines):
                        if any(pat.search(line) for pat in _REDOS_PATTERNS):
                            rel_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": "Potential ReDoS (Regular Expression Denial of Service) vulnerability: Nested quantifiers found in regex.",
                                    "tool": "redos_checker",
                                    "severity": "HIGH",
                                    "line": i + 1,
                                    "category": "security",
                                }
                            )
                except Exception:
                    pass

    # 11. Circular Dependency Detection (from repo_mapper's knowledge graph — avoids redundant rebuild)
    try:
        dep_graph = state.get("dependency_graph", {})
        cycles = dep_graph.get("cycles", [])
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
                            rel_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
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
            elif file.endswith((".go", ".java", ".rs")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    _extract_and_hash_brace_functions(
                        content, file_path, repo_local_path, function_hashes
                    )
                except Exception:
                    pass

    for h, locations in function_hashes.items():
        if len(locations) >= 2:
            for loc in locations:
                other_locs = [loc_item for loc_item in locations if loc_item != loc]
                if not other_locs:
                    continue
                files_str = ", ".join(f"{loc_item[0]}:{loc_item[1]}(L{loc_item[2]})" for loc_item in other_locs)
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

    # 13. Memory Leak Detection — Java (unclosed streams, connections, readers)
    _JAVA_CLOSEABLE_PATTERN = re.compile(
        r"new\s+(FileInputStream|FileOutputStream|BufferedReader|BufferedWriter|"
        r"InputStreamReader|OutputStreamWriter|FileReader|FileWriter|PrintWriter|"
        r"Scanner|Socket|ServerSocket|Connection|PreparedStatement|ResultSet)\s*\("
    )
    for root, _, files in os.walk(repo_local_path):
        if any(skip in root for skip in [".git", "node_modules", "build", "target"]):
            continue
        for file in files:
            if file.endswith(".java"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    rel_path = os.path.relpath(file_path, repo_local_path).replace(
                        "\\", "/"
                    )
                    has_try_with = "try (" in content or "try(" in content
                    for match in _JAVA_CLOSEABLE_PATTERN.finditer(content):
                        match_line = content[: match.start()].count("\n") + 1
                        all_lines = content.splitlines()
                        line_content = (
                            all_lines[match_line - 1]
                            if match_line <= len(all_lines)
                            else ""
                        )
                        if has_try_with and "try" in line_content:
                            continue
                        lines_after = all_lines[match_line : match_line + 50]
                        if not any("close()" in line for line in lines_after):
                            resource_type = match.group(1)
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": f"Potential resource leak: '{resource_type}' opened without try-with-resources or explicit close(). This can leak file handles or connections.",
                                    "tool": "memory_leak_checker",
                                    "severity": "MEDIUM",
                                    "line": match_line,
                                    "category": "performance",
                                }
                            )
                except Exception:
                    pass

    # 14. Go/Rust/Java N+1 and Performance Detection
    _GO_QUERY_PATTERN = re.compile(
        r"\.(Query|QueryRow|Exec|Find|First|Where|Select)\s*\("
    )
    _RUST_QUERY_PATTERN = re.compile(
        r"\.(load|execute|filter|find|get_result|select)\s*\("
    )
    _JAVA_QUERY_PATTERN = re.compile(
        r"\.(executeQuery|executeUpdate|createQuery|createNativeQuery|find|persist|merge|getResultList|getSingleResult)\s*\("
    )
    _GO_LOOP_PATTERN = re.compile(r"^\s*for\s+")
    _JAVA_LOOP_PATTERN = re.compile(r"^\s*(?:for|while)\s*\(")
    for root, _, files in os.walk(repo_local_path):
        if any(skip in root for skip in [".git", "vendor", "target", "node_modules"]):
            continue
        for file in files:
            if file.endswith(".go"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    in_loop = False
                    brace_count = 0
                    for i, line in enumerate(lines):
                        if not in_loop and _GO_LOOP_PATTERN.search(line):
                            in_loop = True
                            brace_count = line.count("{") - line.count("}")
                        elif in_loop:
                            brace_count += line.count("{") - line.count("}")
                            if brace_count <= 0 and "}" in line:
                                in_loop = False
                        if in_loop and _GO_QUERY_PATTERN.search(line):
                            rel_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": "Potential N+1 query (Go): Database query inside a loop. Consider batch fetching or JOIN.",
                                    "tool": "go_perf_checker",
                                    "severity": "HIGH",
                                    "line": i + 1,
                                    "category": "performance",
                                }
                            )
                except Exception:
                    pass
            elif file.endswith(".rs"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    in_loop = False
                    brace_count = 0
                    for i, line in enumerate(lines):
                        if not in_loop and (
                            "for " in line or "while " in line or "loop {" in line
                        ):
                            in_loop = True
                            brace_count = line.count("{") - line.count("}")
                        elif in_loop:
                            brace_count += line.count("{") - line.count("}")
                            if brace_count <= 0 and "}" in line:
                                in_loop = False
                        if in_loop and _RUST_QUERY_PATTERN.search(line):
                            rel_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": "Potential N+1 query (Rust): Database query inside a loop. Consider batch loading.",
                                    "tool": "rust_perf_checker",
                                    "severity": "HIGH",
                                    "line": i + 1,
                                    "category": "performance",
                                }
                            )
                except Exception:
                    pass
            elif file.endswith(".java"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    in_loop = False
                    brace_count = 0
                    for i, line in enumerate(lines):
                        if not in_loop and _JAVA_LOOP_PATTERN.search(line):
                            in_loop = True
                            brace_count = line.count("{") - line.count("}")
                        elif in_loop:
                            brace_count += line.count("{") - line.count("}")
                            if brace_count <= 0 and "}" in line:
                                in_loop = False
                        if in_loop and _JAVA_QUERY_PATTERN.search(line):
                            rel_path = os.path.relpath(
                                file_path, repo_local_path
                            ).replace("\\", "/")
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": "Potential N+1 query (Java): JPA/JDBC query inside a loop. Consider batch fetching, @BatchSize, or JOIN FETCH.",
                                    "tool": "java_perf_checker",
                                    "severity": "HIGH",
                                    "line": i + 1,
                                    "category": "performance",
                                }
                            )
                except Exception:
                    pass

    # 15. HTML/CSS Quality Checks
    _DEPRECATED_TAGS = [
        "<center",
        "<font",
        "<marquee",
        "<blink",
        "<big",
        "<strike",
        "<tt",
    ]
    for root, _, files in os.walk(repo_local_path):
        if any(
            skip in root for skip in [".git", "node_modules", "dist", "build", "venv"]
        ):
            continue
        for file in files:
            if file.endswith(".html"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    rel_path = os.path.relpath(file_path, repo_local_path).replace(
                        "\\", "/"
                    )
                    for i, line in enumerate(content.splitlines()):
                        if 'style="' in line or "style='" in line:
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": "Inline style detected. Consider moving styles to a CSS file for maintainability.",
                                    "tool": "html_quality_checker",
                                    "severity": "LOW",
                                    "line": i + 1,
                                    "category": "quality",
                                }
                            )
                            break
                    for i, line in enumerate(content.splitlines()):
                        lower_line = line.lower()
                        for tag in _DEPRECATED_TAGS:
                            if tag in lower_line:
                                findings.append(
                                    {
                                        "file": rel_path,
                                        "issue": f"Deprecated HTML tag '{tag.lstrip('<')}' found. Use CSS for styling instead.",
                                        "tool": "html_quality_checker",
                                        "severity": "MEDIUM",
                                        "line": i + 1,
                                        "category": "quality",
                                    }
                                )
                                break
                except Exception:
                    pass
            elif file.endswith(".css"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    rel_path = os.path.relpath(file_path, repo_local_path).replace(
                        "\\", "/"
                    )
                    important_count = content.count("!important")
                    if important_count > 5:
                        findings.append(
                            {
                                "file": rel_path,
                                "issue": f"Excessive use of '!important' ({important_count} occurrences). This indicates specificity issues and makes CSS harder to maintain.",
                                "tool": "css_quality_checker",
                                "severity": "MEDIUM",
                                "line": 1,
                                "category": "quality",
                            }
                        )
                    selector_pattern = re.compile(
                        r"^([^{/\n@][^{]*?)\s*\{", re.MULTILINE
                    )
                    selectors = [
                        m.group(1).strip() for m in selector_pattern.finditer(content)
                    ]
                    seen_selectors = {}
                    for sel in selectors:
                        if sel in seen_selectors:
                            findings.append(
                                {
                                    "file": rel_path,
                                    "issue": f"Duplicate CSS selector '{sel}' found. Consider merging rules to reduce redundancy.",
                                    "tool": "css_quality_checker",
                                    "severity": "LOW",
                                    "line": 1,
                                    "category": "quality",
                                }
                            )
                            break
                        seen_selectors[sel] = True
                except Exception:
                    pass

    # ── 16. Dead Code Detection (unused functions / classes / files) ──────
    all_repo_sources: dict[str, str] = {}
    for root_dir, dirs, fnames in os.walk(repo_local_path):
        dirs[:] = [
            d
            for d in dirs
            if d
            not in (
                ".git",
                "node_modules",
                "venv",
                ".venv",
                "__pycache__",
                "dist",
                "build",
                ".next",
                "target",
                "vendor",
            )
        ]
        for fname in fnames:
            if fname.endswith(
                (
                    ".py",
                    ".js",
                    ".jsx",
                    ".ts",
                    ".tsx",
                    ".go",
                    ".java",
                    ".rs",
                    ".html",
                    ".css",
                )
            ):
                fpath = os.path.join(root_dir, fname)
                rel_path = os.path.relpath(fpath, repo_local_path).replace("\\", "/")
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        all_repo_sources[rel_path] = fh.read()
                except Exception:
                    pass

    for rel_path, source in all_repo_sources.items():
        fname = os.path.basename(rel_path)

        if fname.endswith(".py"):
            try:
                tree = ast.parse(source, filename=rel_path)
                defined_funcs: dict[str, int] = {}
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not node.name.startswith("_"):
                            defined_funcs[node.name] = node.lineno

                for func_name, lineno in defined_funcs.items():
                    ref_count = sum(
                        1
                        for node in ast.walk(tree)
                        if isinstance(node, ast.Name)
                        and node.id == func_name
                        and node.lineno != lineno
                    )
                    if ref_count == 0:
                        findings.append(
                            {
                                "file": rel_path,
                                "issue": f"Function '{func_name}' appears to be unused (dead code). Consider removing it.",
                                "tool": "dead_code_detector",
                                "severity": "LOW",
                                "line": lineno,
                                "category": "quality",
                            }
                        )
            except Exception:
                pass

        elif fname.endswith((".js", ".jsx", ".ts", ".tsx")):
            try:
                lines = source.splitlines()
                _js_func_def = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)")
                _js_const_def = re.compile(
                    r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>"
                )
                defined_funcs = {}
                for i, line in enumerate(lines):
                    if line.strip().startswith("export"):
                        continue
                    m = _js_func_def.match(line) or _js_const_def.match(line)
                    if m:
                        defined_funcs[m.group(1)] = i + 1

                for func_name, lineno in defined_funcs.items():
                    ref_count = sum(
                        1
                        for i, line in enumerate(lines, 1)
                        if i != lineno
                        and re.search(r"\b" + re.escape(func_name) + r"\b", line)
                    )
                    if ref_count == 0:
                        findings.append(
                            {
                                "file": rel_path,
                                "issue": f"Function '{func_name}' appears to be unused (dead code). Consider removing it.",
                                "tool": "dead_code_detector",
                                "severity": "LOW",
                                "line": lineno,
                                "category": "quality",
                            }
                        )
            except Exception:
                pass

        elif fname.endswith(".go") and not fname.endswith("_test.go"):
            try:
                lines = source.splitlines()
                _go_func = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([a-z]\w*)\s*\(")
                defined_funcs = {}
                for i, line in enumerate(lines):
                    m = _go_func.match(line)
                    if m and m.group(1) not in ("main", "init"):
                        defined_funcs[m.group(1)] = i + 1
                for func_name, lineno in defined_funcs.items():
                    ref_count = sum(
                        1
                        for i, line in enumerate(lines, 1)
                        if i != lineno
                        and re.search(r"\b" + re.escape(func_name) + r"\b", line)
                    )
                    if ref_count == 0:
                        findings.append(
                            {
                                "file": rel_path,
                                "issue": f"Function '{func_name}' appears to be unused (dead code). Consider removing it.",
                                "tool": "dead_code_detector",
                                "severity": "LOW",
                                "line": lineno,
                                "category": "quality",
                            }
                        )
            except Exception:
                pass

        elif fname.endswith(".java"):
            try:
                lines = source.splitlines()
                _java_func = re.compile(
                    r"^\s*private\s+(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+(\w+)\s*\("
                )
                defined_funcs = {}
                for i, line in enumerate(lines):
                    m = _java_func.match(line)
                    if m:
                        defined_funcs[m.group(1)] = i + 1
                for func_name, lineno in defined_funcs.items():
                    ref_count = sum(
                        1
                        for i, line in enumerate(lines, 1)
                        if i != lineno
                        and re.search(r"\b" + re.escape(func_name) + r"\b", line)
                    )
                    if ref_count == 0:
                        findings.append(
                            {
                                "file": rel_path,
                                "issue": f"Method '{func_name}' appears to be unused (dead code). Consider removing it.",
                                "tool": "dead_code_detector",
                                "severity": "LOW",
                                "line": lineno,
                                "category": "quality",
                            }
                        )
            except Exception:
                pass

        elif fname.endswith(".rs"):
            try:
                lines = source.splitlines()
                _rs_func = re.compile(r"^\s*(?:async\s+)?fn\s+([a-z_]\w*)\s*\(")
                defined_funcs = {}
                for i, line in enumerate(lines):
                    m = _rs_func.match(line)
                    if m and m.group(1) != "main":
                        defined_funcs[m.group(1)] = i + 1
                for func_name, lineno in defined_funcs.items():
                    ref_count = sum(
                        1
                        for i, line in enumerate(lines, 1)
                        if i != lineno
                        and re.search(r"\b" + re.escape(func_name) + r"\b", line)
                    )
                    if ref_count == 0:
                        findings.append(
                            {
                                "file": rel_path,
                                "issue": f"Function '{func_name}' appears to be unused (dead code). Consider removing it.",
                                "tool": "dead_code_detector",
                                "severity": "LOW",
                                "line": lineno,
                                "category": "quality",
                            }
                        )
            except Exception:
                pass

    # HTML/CSS Unused Class Detection
    used_css_classes: set[str] = set()
    for rel_path, source in all_repo_sources.items():
        if rel_path.endswith((".html", ".jsx", ".tsx", ".js")):
            for m in re.finditer(
                r'class(?:Name)?=["\']([^"\']+)["\']', source, re.IGNORECASE
            ):
                for cls in m.group(1).split():
                    used_css_classes.add(cls)

    for rel_path, source in all_repo_sources.items():
        if rel_path.endswith(".css"):
            lines = source.splitlines()
            for i, line in enumerate(lines, 1):
                for m in re.finditer(r"\.([a-zA-Z0-9_-]+)\s*\{", line):
                    cls_name = m.group(1)
                    if cls_name not in used_css_classes and not cls_name.startswith(
                        (":", "root")
                    ):
                        findings.append(
                            {
                                "file": rel_path,
                                "issue": f"CSS class '.{cls_name}' appears to be unused (dead code). Consider removing it.",
                                "tool": "dead_code_detector",
                                "severity": "LOW",
                                "line": i,
                                "category": "quality",
                            }
                        )

    # Whole-Repository Dead File Detection
    entrypoint_names = {
        "main.py",
        "app.py",
        "index.js",
        "index.ts",
        "index.html",
        "main.go",
        "main.java",
        "lib.rs",
        "mod.rs",
        "__init__.py",
        "routes.py",
        "server.py",
        "manage.py",
        "setup.py",
    }
    if len(all_repo_sources) > 1:
        for rel_path, source in all_repo_sources.items():
            fname = os.path.basename(rel_path)
            if (
                fname.lower() in entrypoint_names
                or fname.startswith("test_")
                or fname.endswith(
                    ("_test.go", ".test.js", ".test.ts", "Test.java", "_test.py")
                )
                or "tests/" in rel_path.replace("\\", "/")
                or "test/" in rel_path.replace("\\", "/")
            ):
                continue
            stem = os.path.splitext(fname)[0]
            is_referenced = False
            for other_path, other_content in all_repo_sources.items():
                if other_path == rel_path:
                    continue
                if fname in other_content or stem in other_content:
                    is_referenced = True
                    break
            if not is_referenced:
                findings.append(
                    {
                        "file": rel_path,
                        "issue": f"File '{rel_path}' appears to be unreferenced across the repository (dead file). Consider removing it.",
                        "tool": "dead_file_checker",
                        "severity": "LOW",
                        "line": 1,
                        "category": "quality",
                    }
                )

    # ── 16b. Go Resource Leak Detection ───────────────────────────────────
    _GO_OPEN_PATTERNS = [
        (
            re.compile(
                r"(\w+)\s*(?:,\s*\w+)?\s*(?::=|=)\s*os\.(?:Open|Create|OpenFile)\s*\("
            ),
            "os.Open/Create",
        ),
        (
            re.compile(r"(\w+)\s*(?:,\s*\w+)?\s*(?::=|=)\s*net\.(?:Dial|Listen)\s*\("),
            "net.Dial/Listen",
        ),
        (
            re.compile(r"(\w+)\s*(?:,\s*\w+)?\s*(?::=|=)\s*http\.(?:Get|Post|Do)\s*\("),
            "http.Get/Post",
        ),
    ]
    for root_dir, dirs, fnames in os.walk(repo_local_path):
        dirs[:] = [
            d for d in dirs if d not in (".git", "node_modules", "vendor", "target")
        ]
        for fname in fnames:
            if not fname.endswith(".go"):
                continue
            fpath = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(fpath, repo_local_path).replace("\\", "/")
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    for pattern, desc in _GO_OPEN_PATTERNS:
                        m = pattern.search(line)
                        if m:
                            var_name = m.group(1)
                            # Check if a defer <var>.Close() exists in the next 5 lines
                            lookahead = "\n".join(lines[i + 1 : i + 6])
                            if (
                                f"defer {var_name}.Close()" not in lookahead
                                and f"defer {var_name}.Body.Close()" not in lookahead
                            ):
                                findings.append(
                                    {
                                        "file": rel_path,
                                        "issue": f"Potential resource leak (Go): {desc} result '{var_name}' opened without a subsequent 'defer {var_name}.Close()'.",
                                        "tool": "go_leak_detector",
                                        "severity": "MEDIUM",
                                        "line": i + 1,
                                        "category": "performance",
                                    }
                                )
                            break
            except Exception:
                pass

    # ── 17. Long Methods Detection ────────────────────────────────────────
    LONG_METHOD_THRESHOLD = 50  # lines
    for root_dir, dirs, fnames in os.walk(repo_local_path):
        dirs[:] = [
            d
            for d in dirs
            if d
            not in (
                ".git",
                "node_modules",
                "venv",
                ".venv",
                "__pycache__",
                "dist",
                "build",
                ".next",
                "target",
            )
        ]
        for fname in fnames:
            fpath = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(fpath, repo_local_path).replace("\\", "/")
            ext = os.path.splitext(fname)[1]

            if ext == ".py":
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        source = fh.read()
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if hasattr(node, "end_lineno") and node.end_lineno:
                                length = node.end_lineno - node.lineno + 1
                                if length > LONG_METHOD_THRESHOLD:
                                    findings.append(
                                        {
                                            "file": rel_path,
                                            "issue": f"Function '{node.name}' is {length} lines long (>{LONG_METHOD_THRESHOLD}). Consider refactoring.",
                                            "tool": "long_method_detector",
                                            "severity": "LOW",
                                            "line": node.lineno,
                                            "category": "quality",
                                        }
                                    )
                except (SyntaxError, Exception):
                    pass

            elif ext in (".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs"):
                # Brace-matched function length check
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        lines = fh.readlines()

                    func_pattern = None
                    if ext in (".js", ".jsx", ".ts", ".tsx"):
                        func_pattern = re.compile(
                            r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"
                        )
                    elif ext == ".java":
                        func_pattern = re.compile(
                            r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+(\w+)\s*\("
                        )
                    elif ext == ".go":
                        func_pattern = re.compile(
                            r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("
                        )
                    elif ext == ".rs":
                        func_pattern = re.compile(
                            r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"
                        )

                    if func_pattern:
                        i = 0
                        while i < len(lines):
                            m = func_pattern.match(lines[i])
                            if m and "{" in lines[i]:
                                func_name = m.group(1)
                                start = i
                                brace_depth = 0
                                for j in range(i, len(lines)):
                                    brace_depth += lines[j].count("{") - lines[j].count(
                                        "}"
                                    )
                                    if brace_depth <= 0 and j > i:
                                        length = j - start + 1
                                        if length > LONG_METHOD_THRESHOLD:
                                            findings.append(
                                                {
                                                    "file": rel_path,
                                                    "issue": f"Function '{func_name}' is {length} lines long (>{LONG_METHOD_THRESHOLD}). Consider refactoring.",
                                                    "tool": "long_method_detector",
                                                    "severity": "LOW",
                                                    "line": start + 1,
                                                    "category": "quality",
                                                }
                                            )
                                        i = j + 1
                                        break
                                else:
                                    i += 1
                            else:
                                i += 1
                except Exception:
                    pass

    # ── 18. Built-in Hardcoded Secrets Scanner ────────────────────────────
    _SECRET_PATTERNS = [
        (
            re.compile(
                r"""(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]""", re.IGNORECASE
            ),
            "Hardcoded password",
        ),
        (
            re.compile(
                r"""(?:secret|token|api_key|apikey|api[-_]?secret)\s*[:=]\s*['"][^'"]{8,}['"]""",
                re.IGNORECASE,
            ),
            "Hardcoded secret/token",
        ),
        (re.compile(r"""AKIA[0-9A-Z]{16}"""), "AWS Access Key ID"),
        (
            re.compile(r"""-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"""),
            "Private key in source",
        ),
        (re.compile(r"""ghp_[A-Za-z0-9]{36}"""), "GitHub personal access token"),
        (re.compile(r"""gsk_[A-Za-z0-9]{20,}"""), "Groq API key"),
        (re.compile(r"""sk-[A-Za-z0-9]{20,}"""), "OpenAI-style API key"),
        (re.compile(r"""xox[bprs]-[A-Za-z0-9\-]{10,}"""), "Slack token"),
    ]
    _SECRET_EXTENSIONS = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".go",
        ".rs",
        ".yml",
        ".yaml",
        ".json",
        ".env",
        ".cfg",
        ".ini",
        ".toml",
    }
    _SECRET_SKIP_DIRS = {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        "target",
    }

    for root_dir, dirs, fnames in os.walk(repo_local_path):
        dirs[:] = [d for d in dirs if d not in _SECRET_SKIP_DIRS]
        for fname in fnames:
            ext = os.path.splitext(fname)[1]
            if ext not in _SECRET_EXTENSIONS:
                continue
            # Skip example/template env files
            if fname in (".env.example", ".env.sample", ".env.template"):
                continue
            fpath = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(fpath, repo_local_path).replace("\\", "/")
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        for pattern, description in _SECRET_PATTERNS:
                            if pattern.search(line):
                                findings.append(
                                    {
                                        "file": rel_path,
                                        "issue": f"{description} detected on line {lineno}. Avoid hardcoding credentials in source code.",
                                        "tool": "secrets_scanner",
                                        "severity": "HIGH",
                                        "line": lineno,
                                        "category": "security",
                                    }
                                )
                                break  # One finding per line is enough
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
                        rel_path = os.path.relpath(file_path, repo_local_path).replace(
                            "\\", "/"
                        )
                        if h not in function_hashes:
                            function_hashes[h] = []
                        function_hashes[h].append((rel_path, name, start + 1))
                    i = j + 1
                    break
            else:
                i += 1
        else:
            i += 1


def _extract_and_hash_brace_functions(
    content: str, file_path: str, repo_local_path: str, function_hashes: dict
):
    """Extract Go/Java/Rust function bodies using regex + brace matching and hash them for duplicate detection."""
    import hashlib

    lines = content.splitlines()
    ext = os.path.splitext(file_path)[1]

    if ext == ".go":
        func_pattern = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?\w+\s*\(")
    elif ext == ".java":
        func_pattern = re.compile(
            r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?[\w<>\[\]]+\s+\w+\s*\("
        )
    elif ext == ".rs":
        func_pattern = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+\w+")
    else:
        return

    i = 0
    while i < len(lines):
        m = func_pattern.match(lines[i].strip())
        if m and "{" in lines[i]:
            name_match = re.search(r"(?:func|fn)\s+(\w+)", lines[i])
            if not name_match:
                name_match = re.search(r"(\w+)\s*\(", lines[i])
            name = name_match.group(1) if name_match else f"block_L{i + 1}"
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
                        rel_path = os.path.relpath(file_path, repo_local_path).replace(
                            "\\", "/"
                        )
                        if h not in function_hashes:
                            function_hashes[h] = []
                        function_hashes[h].append((rel_path, name, start + 1))
                    i = j + 1
                    break
            else:
                i += 1
        else:
            i += 1
