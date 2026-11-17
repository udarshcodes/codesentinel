import os
import json
import shlex
import re
from models.pipeline_state import PipelineState
from tools.confidence_calc import calculate_pipeline_confidence
from tools.sandbox_runner import run_sandboxed_subprocess
from tools.safe_repo import safe_path_exists, safe_read_text

# Command registry to prevent arbitrary command injection.
# We map the base command to the exact allowed executable and arguments.
ALLOWED_TEST_COMMANDS = {
    "pytest": {"exec": ["python", "-m", "pytest"], "allow_args": True},
    "npm test": {"exec": ["npm", "test"], "allow_args": False},
    "npm run test": {"exec": ["npm", "run", "test"], "allow_args": False},
    "npx jest": {"exec": ["node_modules/.bin/jest"], "allow_args": True},
    "go test": {"exec": ["go", "test"], "allow_args": True},
    "mvn test": {"exec": ["mvn", "test"], "allow_args": False},
    "gradle test": {"exec": ["gradle", "test"], "allow_args": False},
    "./gradlew test": {"exec": ["./gradlew", "test"], "allow_args": False},
    "cargo test": {"exec": ["cargo", "test"], "allow_args": False},
    "dotnet test": {"exec": ["dotnet", "test"], "allow_args": False},
    "ruby -Itest": {"exec": ["ruby", "-Itest"], "allow_args": True},
    "python -m pytest": {"exec": ["python", "-m", "pytest"], "allow_args": True},
    "python -m unittest": {"exec": ["python", "-m", "unittest"], "allow_args": True},
}


def _validate_and_parse_cmd(cmd_str: str) -> list[str]:
    """Strictly validates a test command against the registry and parses it into a list."""
    cleaned = cmd_str.strip()
    
    # Check exact match first
    if cleaned in ALLOWED_TEST_COMMANDS:
        return ALLOWED_TEST_COMMANDS[cleaned]["exec"]
        
    # Check if it starts with an allowed base command that permits extra arguments
    for base, config in ALLOWED_TEST_COMMANDS.items():
        if config["allow_args"] and cleaned.startswith(base + " "):
            try:
                parsed = shlex.split(cleaned)
                base_len = len(shlex.split(base))
                return config["exec"] + parsed[base_len:]
            except ValueError:
                return []
    return []


async def agent_validator(state: PipelineState):
    validation_results = state.get("validation_results", [])
    if state.get("approval_decision") == "rejected":
        return {"validation_results": validation_results}

    repo_local_path = state.get("repo_local_path", "")
    patches = [patch for patch in state.get("patches", []) if not patch.get("excluded_from_validation")]

    if not patches or not repo_local_path:
        retry_count = state.get("retry_count", 0)
        if state.get("repair_plan"):
            retry_count += 1
        return {"validation_results": validation_results, "retry_count": retry_count}

    from tools.project_dependencies import prepare_python_dependencies
    dependencies = prepare_python_dependencies(repo_local_path)
    if dependencies["status"] == "failed":
        conflict = any(marker in dependencies["error"] for marker in ("ResolutionImpossible", "conflicting dependencies"))
        manifests = {patch.get("file") for patch in patches if patch.get("applied") and patch.get("file") in state.get("manifest_originals", {})}
        if conflict and manifests:
            from tools.dependency_transaction import rollback_dependencies
            restored = rollback_dependencies(state, manifests, "Proposed dependency versions conflict. Original dependencies restored; compatible upgrades require manual review.")
            validation = await agent_validator({**state, **restored})
            return {**restored, **validation}
        syntax_failure = dependencies['error'].startswith('TOMLDecodeError:')
        result = {"passed": False, "infrastructure_error": not syntax_failure, "suite_failed": not syntax_failure,
                  "build_failed": syntax_failure, "files_passed": 0, "files_validated": 0,
                  "failed_issue_ids": [patch.get('patch_id') for patch in patches if syntax_failure and patch.get('file', '').endswith('pyproject.toml')],
                  "logs": "Dependency preparation failed: " + dependencies["error"]}
        return {"validation_results": list(validation_results) + [result], "security_verified": False,
                'retry_count': state.get('retry_count', 0) + int(syntax_failure)}

    all_passed = True
    logs_list = []
    failed_issue_ids = []
    passed_files = set()
    deferred_files = {}
    covered_projects = set()

    # Earlier rejected attempts must not invalidate a later successful repair.
    latest_attempts = {}
    for index, patch in enumerate(patches):
        latest_attempts[patch.get("patch_id", (patch.get("file"), index))] = patch
    for patch in latest_attempts.values():
        logs_len_before = len(logs_list)
        target_file = patch.get("file", "")

        if not safe_path_exists(repo_local_path, target_file):
            logs_list.append(f"[FAILED] {target_file} - file not found")
            all_passed = False
            failed_issue_ids.append(patch.get("patch_id"))
            continue

        if not patch.get("applied", True):
            logs_list.append(f"[FAILED] {target_file} - patch failed to apply, file is unmodified")
            all_passed = False
            failed_issue_ids.append(patch.get("patch_id"))
            continue

        # Python files: check syntax with py_compile
        if target_file.endswith(".py"):
            res = run_sandboxed_subprocess(["python", "-m", "py_compile", target_file], cwd=repo_local_path, timeout=30)
            if res["status"] == "SUCCESS":
                logs_list.append(f"[PASSED] {target_file} - syntax OK")
            else:
                logs_list.append(f"[{res['status']}] {target_file} - {res['stderr']}")
                all_passed = False

        # JS files: syntax check with node --check (only plain JS)
        elif target_file.endswith((".js", ".mjs")):
            res = run_sandboxed_subprocess(["node", "--check", target_file], cwd=repo_local_path, timeout=30)
            if res["status"] == "SUCCESS":
                logs_list.append(f"[PASSED] {target_file} - syntax OK")
            elif "Unexpected token" in res["stderr"] or "Cannot use import" in res["stderr"]:
                logs_list.append(f"[DEFERRED] {target_file} - ES module / JSX requires project build")
            elif res["status"] == "UNAVAILABLE":
                logs_list.append(f"[UNAVAILABLE] {target_file} - node not available for syntax check")
            else:
                logs_list.append(f"[{res['status']}] {target_file} - {res['stderr']}")
                all_passed = False

        # JSX/TSX files: skip node --check (Node.js can't parse JSX)
        elif target_file.endswith((".jsx", ".tsx")):
            logs_list.append(f"[DEFERRED] {target_file} - JSX/TSX requires project build")

        # TypeScript files: syntax check with tsc --noEmit
        elif target_file.endswith(".ts"):
            if node_build_project(repo_local_path, target_file):
                logs_list.append(f"[DEFERRED] {target_file} - TypeScript requires project build")
            else:
                tsc_bin = os.path.join(repo_local_path, "node_modules", ".bin", "tsc")
                if os.name == 'nt':
                    tsc_bin += ".cmd"
                
                if not os.path.exists(tsc_bin):
                    logs_list.append(f"[UNAVAILABLE] {target_file} - local tsc not found. Avoiding dynamic npx --yes execution for security.")
                else:
                    tsconfig_path = os.path.join(repo_local_path, "tsconfig.json")
                    if os.path.exists(tsconfig_path):
                        tsc_cmd = ["./node_modules/.bin/tsc", "--noEmit", "--skipLibCheck", "--project", "tsconfig.json"]
                    else:
                        tsc_cmd = ["./node_modules/.bin/tsc", "--noEmit", "--allowJs", "--checkJs", "--skipLibCheck", target_file]

                    res = run_sandboxed_subprocess(tsc_cmd, cwd=repo_local_path, timeout=60)
                    if res["status"] == "SUCCESS":
                        logs_list.append(f"[PASSED] {target_file} - TypeScript syntax OK")
                    else:
                        logs_list.append(f"[{res['status']}] {target_file} - {res['stderr'][:300]}")
                        all_passed = False

        # Go files: syntax check with go vet
        elif target_file.endswith(".go"):
            go_dir = os.path.dirname(target_file)
            go_vet_path = "./" + go_dir + "/..." if go_dir else "./..."
            res = run_sandboxed_subprocess(["go", "vet", go_vet_path], cwd=repo_local_path, timeout=60)
            if res["status"] == "SUCCESS":
                logs_list.append(f"[PASSED] {target_file} - Go vet OK")
            elif res["status"] == "UNAVAILABLE":
                logs_list.append(f"[UNAVAILABLE] {target_file} - go vet not available")
            else:
                logs_list.append(f"[{res['status']}] {target_file} - {res['stderr'][:300]}")
                all_passed = False

        # Java files: syntax check with javac (dry run)
        elif target_file.endswith(".java"):
            if os.path.exists(os.path.join(repo_local_path, "pom.xml")) or os.path.exists(os.path.join(repo_local_path, "build.gradle")) or os.path.exists(os.path.join(repo_local_path, "build.gradle.kts")):
                logs_list.append(f"[DEFERRED] {target_file} - Java requires project build")

            else:
                import tempfile as _tmpmod
                import shutil as _shutil
                _javac_tmp = _tmpmod.mkdtemp(prefix="cs_javac_")
                try:
                    res = run_sandboxed_subprocess(["javac", "-d", _javac_tmp, target_file], cwd=repo_local_path, timeout=60)
                    if res["status"] == "SUCCESS":
                        logs_list.append(f"[PASSED] {target_file} - Java syntax OK")
                    elif res["status"] == "UNAVAILABLE":
                        logs_list.append(f"[UNAVAILABLE] {target_file} - javac not available")
                    else:
                        logs_list.append(f"[{res['status']}] {target_file} - {res['stderr'][:300]}")
                        all_passed = False
                finally:
                    _shutil.rmtree(_javac_tmp, ignore_errors=True)

        # Rust files: validated by cargo build step
        elif target_file.endswith(".rs"):
            logs_list.append(f"[DEFERRED] {target_file} - Rust requires cargo build")

        elif target_file.endswith(".toml") or os.path.basename(target_file) in ("uv.lock", "poetry.lock", "Cargo.lock"):
            try:
                import tomllib
                tomllib.loads(safe_read_text(repo_local_path, target_file))
                logs_list.append(f"[PASSED] {target_file} - TOML parsed OK")
            except (ValueError, OSError) as error:
                logs_list.append(f"[FAILED] {target_file} - TOML parse error: {error}")
                all_passed = False

        elif target_file.endswith(".json"):
            try:
                json.loads(safe_read_text(repo_local_path, target_file))
                logs_list.append(f"[PASSED] {target_file} - JSON parsed OK")
            except (ValueError, OSError) as error:
                logs_list.append(f"[FAILED] {target_file} - JSON parse error: {error}")
                all_passed = False

        # HTML files: basic structure check
        elif target_file.endswith((".html", ".htm")):
            try:
                content = safe_read_text(repo_local_path, target_file)
                from html.parser import HTMLParser
                parser = HTMLParser()
                parser.feed(content)
                logs_list.append(f"[PASSED] {target_file} - HTML parsed OK")
            except Exception as e:
                logs_list.append(f"[FAILED] {target_file} - HTML parse error: {e}")
                all_passed = False

        # CSS files: check for balanced braces
        elif target_file.endswith(".css"):
            try:
                content = safe_read_text(repo_local_path, target_file)
                open_count = content.count("{")
                close_count = content.count("}")
                if open_count == close_count:
                    logs_list.append(f"[PASSED] {target_file} - CSS braces balanced ({open_count} blocks)")
                else:
                    logs_list.append(f"[FAILED] {target_file} - CSS braces unbalanced (opened: {open_count}, closed: {close_count})")
                    all_passed = False
            except Exception as e:
                logs_list.append(f"[ERROR] {target_file} - CSS read error: {e}")
                all_passed = False
        else:
            logs_list.append(f"[SKIPPED] {target_file} - no validator for this file type")

        file_logs = logs_list[logs_len_before:]
        if any("[DEFERRED]" in log for log in file_logs):
            language = "java" if target_file.endswith(".java") else "rust" if target_file.endswith(".rs") else "node"
            project = node_build_project(repo_local_path, target_file) if language == "node" else os.path.abspath(repo_local_path)
            entry = deferred_files.setdefault(target_file, {"project": (language, project), "ids": []})
            entry["ids"].append(patch.get("patch_id"))
        if any(any(f"[{status}]" in log for status in ("FAILED", "ERROR", "TIMEOUT", "UNAVAILABLE", "SKIPPED")) for log in file_logs):
            failed_issue_ids.append(patch.get("patch_id"))
            passed_files.discard(target_file)
            all_passed = False
        elif any("[PASSED]" in log for log in file_logs):
            passed_files.add(target_file)

    # Build verification stage
    build_passed = True
    pkg_paths = []
    for candidate in ["frontend/package.json", "backend/package.json", "package.json"]:
        p = os.path.join(repo_local_path, candidate.replace("/", os.sep))
        if os.path.exists(p):
            pkg_paths.append(p)

    for pkg_path in pkg_paths:
        build_cwd = os.path.dirname(pkg_path)
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)

            from tools.node_dependencies import prepare_node_dependencies
            prepared = prepare_node_dependencies(build_cwd)
            res = {"status": "SUCCESS" if prepared["status"] == "ready" else "FAILED",
                   "stdout": "", "stderr": prepared.get("error", "")}

            if res["status"] != "SUCCESS":
                diagnostic = res.get("stdout", "") + "\n" + res.get("stderr", "")
                changed_manifests = [p for p in latest_attempts.values() if p.get("applied") and
                                     p.get("file", "").replace("\\", "/") in {
                                         os.path.relpath(pkg_path, repo_local_path).replace("\\", "/"),
                                         os.path.relpath(os.path.join(build_cwd, "package-lock.json"), repo_local_path).replace("\\", "/")}]
                repair_conflict = bool(changed_manifests) and any(code in diagnostic for code in ("ERESOLVE", "ETARGET"))
                result = {"passed": False, "infrastructure_error": not repair_conflict, "suite_failed": True,
                          "build_failed": False, "files_passed": len(passed_files), "files_validated": len({p.get("file") for p in latest_attempts.values() if p.get("file")}),
                          "failed_issue_ids": [p.get("patch_id") for p in changed_manifests] if repair_conflict else [], "tests_executed": False,
                          "logs": "Node dependency preparation failed. A synchronized npm lockfile with supported registry packages is required.\n" +
                                  (res.get("stdout", "") + "\n" + res.get("stderr", ""))[-6000:]}
                return {"validation_results": list(validation_results) + [result], "security_verified": False}

            project_built = False
            if "scripts" in pkg and "build" in pkg["scripts"]:
                res = run_sandboxed_subprocess(
                    ["npm", "run", "build"],
                    cwd=build_cwd,
                    timeout=60
                )
                if res["status"] != "SUCCESS":
                    build_passed = False
                    logs_list.append(f"[{res['status']}] Build verification failed (npm run build in {build_cwd}):\n{res['stderr'][:500]}")
                    all_passed = False
                else:
                    logs_list.append(f"[PASSED] Build verification passed (npm run build in {build_cwd})")
                    project_built = True
            if "lint" in pkg.get("scripts", {}) and build_passed:
                lint = run_sandboxed_subprocess(["npm", "run", "lint"], cwd=build_cwd, timeout=60)
                logs_list.append(f"[{lint['status']}] Lint verification (npm run lint in {build_cwd}):\n" +
                                 (lint.get("stdout", "") + "\n" + lint.get("stderr", ""))[-6000:])
                if lint["status"] != "SUCCESS":
                    build_passed = False
                    all_passed = False
            if project_built and build_passed:
                covered_projects.add(("node", os.path.abspath(build_cwd)))
        except Exception as e:
            logs_list.append(f"[ERROR] package.json build error in {build_cwd}: {e}")
            build_passed = False
            all_passed = False

    # A dependency-only pyproject describes an app, not necessarily a package.
    python_package = safe_path_exists(repo_local_path, "setup.py")
    if safe_path_exists(repo_local_path, "pyproject.toml"):
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            project_config = tomllib.loads(safe_read_text(repo_local_path, "pyproject.toml"))
            python_package = python_package or "build-system" in project_config
        except Exception as error:
            logs_list.append(f"[ERROR] Invalid pyproject.toml: {error}")
            build_passed = False
            all_passed = False
    if python_package:
        res = run_sandboxed_subprocess(
            ["python", "-m", "build"],
            cwd=repo_local_path,
            timeout=60
        )
        if res["status"] != "SUCCESS":
            build_passed = False
            logs_list.append(f"[{res['status']}] Build verification failed (python -m build):\n{res['stderr'][:500]}")
            all_passed = False
        else:
            logs_list.append("[PASSED] Build verification passed (python -m build)")

    if os.path.exists(os.path.join(repo_local_path, "pom.xml")):
        res = run_sandboxed_subprocess(
            ["mvn", "package", "-DskipTests"],
            cwd=repo_local_path,
            timeout=60
        )
        if res["status"] != "SUCCESS":
            build_passed = False
            logs_list.append(f"[{res['status']}] Build verification failed (mvn package):\n{res['stdout'][-500:]}")
            all_passed = False
        else:
            logs_list.append("[PASSED] Build verification passed (mvn package)")
            covered_projects.add(("java", os.path.abspath(repo_local_path)))

    if os.path.exists(os.path.join(repo_local_path, "build.gradle")) or os.path.exists(os.path.join(repo_local_path, "build.gradle.kts")):
        gradle_cmd = ["./gradlew", "assemble"] if os.path.exists(os.path.join(repo_local_path, "gradlew")) else ["gradle", "assemble"]
        res = run_sandboxed_subprocess(
            gradle_cmd,
            cwd=repo_local_path,
            timeout=60
        )
        if res["status"] != "SUCCESS":
            build_passed = False
            logs_list.append(f"[{res['status']}] Build verification failed ({' '.join(gradle_cmd)}):\n{res['stdout'][-500:]}")
            all_passed = False
        else:
            logs_list.append(f"[PASSED] Build verification passed ({' '.join(gradle_cmd)})")
            covered_projects.add(("java", os.path.abspath(repo_local_path)))

    if os.path.exists(os.path.join(repo_local_path, "go.mod")):
        res = run_sandboxed_subprocess(
            ["go", "build", "./..."],
            cwd=repo_local_path,
            timeout=120
        )
        if res["status"] != "SUCCESS":
            build_passed = False
            logs_list.append(f"[{res['status']}] Build verification failed (go build):\n{res['stderr'][:500]}")
            all_passed = False
        else:
            logs_list.append("[PASSED] Build verification passed (go build)")

    if os.path.exists(os.path.join(repo_local_path, "Cargo.toml")):
        res = run_sandboxed_subprocess(
            ["cargo", "build"],
            cwd=repo_local_path,
            timeout=120
        )
        if res["status"] != "SUCCESS":
            build_passed = False
            logs_list.append(f"[{res['status']}] Build verification failed (cargo build):\n{res['stderr'][:500]}")
            all_passed = False
        else:
            logs_list.append("[PASSED] Build verification passed (cargo build)")
            covered_projects.add(("rust", os.path.abspath(repo_local_path)))

    for file, deferred in deferred_files.items():
        if deferred["project"] in covered_projects:
            passed_files.add(file)
            logs_list.append(f"[PASSED] {file} - validated by configured project build/lint")
        else:
            all_passed = False
            failed_issue_ids.extend(deferred["ids"])
            logs_list.append(f"[UNAVAILABLE] {file} - no successful configured project build covered this file")

    test_logs = ""
    suite_failed = False
    tests_run = 0
    if not build_passed:
        test_logs = "Tests skipped due to build failure. Validation failed."
    else:
        # Dynamic test suite execution
        knowledge_graph = state.get("knowledge_graph", {})
        test_framework = knowledge_graph.get("test_framework", "")

        tests_run = 0

        # Try executing configured test framework first
        if test_framework:
            cmd = _validate_and_parse_cmd(test_framework)
            if cmd:
                # We skip venv creation for dynamically configured python tests to avoid complexity and reliance on pip.
                # All tests should run purely through the isolated runner.
                res = run_sandboxed_subprocess(cmd, cwd=repo_local_path, timeout=60)
                
                test_logs += f"\n[{test_framework} Results]\n{(res.get('stdout', '') + '\n' + res.get('stderr', ''))[-6000:]}\n"
                
                if res["status"] != "SUCCESS":
                    suite_failed = True
                    all_passed = False
                tests_run += 1
            else:
                test_logs += f"\nTest command '{test_framework}' was rejected by the command registry for security reasons.\n"
                suite_failed = True
                all_passed = False

        if tests_run == 0:
            # Intelligent fallback: Execute tests for all relevant ecosystems found
            if os.path.exists(os.path.join(repo_local_path, "pyproject.toml")) or os.path.exists(os.path.join(repo_local_path, "setup.py")) or os.path.exists(os.path.join(repo_local_path, "requirements.txt")):
                res = run_sandboxed_subprocess(["python", "-m", "pytest", "--tb=short", "-q"], cwd=repo_local_path, timeout=60)
                test_logs += f"\n[Python Test Results]\n{(res.get('stdout', '') + '\n' + res.get('stderr', ''))[-6000:]}\n"
                if res["status"] != "SUCCESS" and "no tests ran" not in test_logs.lower() and "zero tests" not in test_logs.lower():
                    suite_failed = True
                    all_passed = False
                tests_run += 1

            for candidate in ["frontend/package.json", "backend/package.json", "package.json"]:
                p = os.path.join(repo_local_path, candidate.replace("/", os.sep))
                if os.path.exists(p):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            pkg = json.load(f)
                        if "scripts" in pkg and "test" in pkg["scripts"] and 'echo "Error: no test specified"' not in pkg["scripts"]["test"]:
                            res = run_sandboxed_subprocess(["npm", "test"], cwd=os.path.dirname(p), timeout=60)
                            test_logs += f"\n[Node.js Test Results in {candidate}]\n{(res.get('stdout', '') + '\n' + res.get('stderr', ''))[-6000:]}\n"
                            if res["status"] != "SUCCESS":
                                suite_failed = True
                                all_passed = False
                            tests_run += 1
                    except Exception as e:
                        test_logs += f"\n[Node.js Test Error in {candidate}] {e}\n"
                        suite_failed = True
                        all_passed = False

            if os.path.exists(os.path.join(repo_local_path, "go.mod")):
                res = run_sandboxed_subprocess(["go", "test", "./..."], cwd=repo_local_path, timeout=60)
                test_logs += f"\n[Go Test Results]\n{(res.get('stdout', '') + '\n' + res.get('stderr', ''))[-6000:]}\n"
                if res["status"] != "SUCCESS" and "no test files" not in test_logs.lower():
                    suite_failed = True
                    all_passed = False
                tests_run += 1

            if os.path.exists(os.path.join(repo_local_path, "build.gradle")) or os.path.exists(os.path.join(repo_local_path, "build.gradle.kts")):
                cmd = ["./gradlew", "test"] if os.path.exists(os.path.join(repo_local_path, "gradlew")) else ["gradle", "test"]
                res = run_sandboxed_subprocess(cmd, cwd=repo_local_path, timeout=60)
                test_logs += f"\n[Gradle Test Results]\n{(res.get('stdout', '') + '\n' + res.get('stderr', ''))[-6000:]}\n"
                if res["status"] != "SUCCESS":
                    suite_failed = True
                    all_passed = False
                tests_run += 1
            elif os.path.exists(os.path.join(repo_local_path, "pom.xml")):
                res = run_sandboxed_subprocess(["mvn", "test"], cwd=repo_local_path, timeout=60)
                test_logs += f"\n[Maven Test Results]\n{(res.get('stdout', '') + '\n' + res.get('stderr', ''))[-6000:]}\n"
                if res["status"] != "SUCCESS":
                    suite_failed = True
                    all_passed = False
                tests_run += 1

            if os.path.exists(os.path.join(repo_local_path, "Cargo.toml")):
                res = run_sandboxed_subprocess(["cargo", "test"], cwd=repo_local_path, timeout=60)
                test_logs += f"\n[Rust Test Results]\n{(res.get('stdout', '') + '\n' + res.get('stderr', ''))[-6000:]}\n"
                if res["status"] != "SUCCESS":
                    suite_failed = True
                    all_passed = False
                tests_run += 1

            if tests_run == 0:
                test_logs += "\nNo recognized test frameworks found to execute.\n"

    retry_count = state.get("retry_count", 0)
    unresolvable = False
    unresolvable_fixes = state.get("unresolvable_fixes", [])
    touched_symbols = state.get("touched_symbols", {})

    if not all_passed or not build_passed or suite_failed:
        if patches:
            latest_patch = patches[-1]
            issue_id = latest_patch.get("patch_id")
            failure_summary = "\n".join(logs_list) + "\nTest Results:\n" + test_logs
            if issue_id in touched_symbols:
                touched_symbols[issue_id]["last_failure_reason"] = failure_summary

        retry_count += 1
        if retry_count >= 3:
            unresolvable = True
            if patches:
                unresolvable_fixes.append(patches[-1].get("patch_id", 0))

    new_validation_results = list(validation_results)
    files_validated = len({p.get("file") for p in latest_attempts.values()})
    files_passed = len(passed_files)

    last_patch_id = patches[-1].get("patch_id", 0) if patches else 0

    if not all_passed and not failed_issue_ids and patches:
        failed_issue_ids.append(last_patch_id)

    investigated_issues = state.get("investigated_issues", [])
    issue = next((i for i in investigated_issues if i.get("id") == last_patch_id), {})
    issue_desc = issue.get("description", str(issue))

    new_validation_results.append(
        {
            "patch_id": last_patch_id,
            "passed": all_passed,
            "unresolvable": unresolvable,
            "logs": "\n".join(logs_list) + "\n\nTest Results:\n" + test_logs,
            "files_validated": files_validated,
            "files_passed": files_passed,
            "failed_issue_ids": failed_issue_ids,
            "build_failed": not build_passed,
            "suite_failed": suite_failed,
            "tests_executed": tests_run > 0 and not suite_failed and not re.search(r"\b(?:ran\s+)?0\s+tests?\b|no tests ran|zero tests|no tests found", test_logs.lower()),
            "issue_description": issue_desc,
        }
    )

    security_clean = state.get("security_verified", False)
    confidence = calculate_pipeline_confidence(
        state,
        tests_passed=files_passed,
        tests_total=files_validated,
        security_clean=security_clean,
        chroma_score=0.0,
    )

    return {
        "validation_results": new_validation_results,
        "confidence_score": confidence,
        "unresolvable_fixes": unresolvable_fixes,
        "retry_count": retry_count,
        "touched_symbols": touched_symbols,
    }


def node_build_project(repo, target_file):
    current = os.path.dirname(os.path.abspath(os.path.join(repo, target_file)))
    root = os.path.abspath(repo)
    while os.path.commonpath([root, current]) == root:
        relative = os.path.relpath(os.path.join(current, "package.json"), root)
        if safe_path_exists(root, relative):
            try:
                pkg = json.loads(safe_read_text(root, relative))
                return current if pkg.get("scripts", {}).get("build") else None
            except (ValueError, OSError):
                return None
        if current == root:
            break
        current = os.path.dirname(current)
    return None
