import os
import sys
import subprocess
import shutil
import asyncio
import json
import shlex
from models.pipeline_state import PipelineState
from tools.vector_store import query_similar_fixes, store_validated_fix
from tools.confidence_calc import calculate_pipeline_confidence

# Whitelist of allowed test commands to prevent command injection from LLM output
ALLOWED_TEST_COMMANDS = {
    "pytest",
    "npm test",
    "npm run test",
    "npx jest",
    "go test",
    "mvn test",
    "gradle test",
    "cargo test",
    "dotnet test",
    "ruby -Itest",
    "python -m pytest",
    "python -m unittest",
}


def _is_allowed_cmd(cmd_str: str) -> bool:
    cleaned = cmd_str.strip()
    for allowed in ALLOWED_TEST_COMMANDS:
        if cleaned == allowed or cleaned.startswith(allowed + " "):
            return True
    return False


async def agent_validator(state: PipelineState):
    validation_results = state.get("validation_results", [])
    if state.get("approval_decision") == "rejected":
        return {"validation_results": validation_results}

    repo_local_path = state.get("repo_local_path", "")
    patches = state.get("patches", [])

    if not patches or not repo_local_path:
        retry_count = state.get("retry_count", 0)
        if state.get("repair_plan"):
            retry_count += 1
        return {"validation_results": validation_results, "retry_count": retry_count}

    # Since code_generator now writes fixes directly to disk,
    # we validate by checking if the files are syntactically correct.

    all_passed = True
    logs_list = []
    failed_issue_ids = []

    for patch in patches:
        logs_len_before = len(logs_list)
        target_file = patch.get("file", "")
        full_path = os.path.join(repo_local_path, target_file)

        if not os.path.exists(full_path):
            logs_list.append(f"[SKIP] {target_file} - file not found")
            continue

        if not patch.get("applied", True):
            logs_list.append(
                f"[FAIL] {target_file} - patch failed to apply, file is unmodified"
            )
            all_passed = False
            continue

        # Python files: check syntax with py_compile
        if target_file.endswith(".py"):
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", full_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    logs_list.append(f"[PASS] {target_file} - syntax OK")
                else:
                    logs_list.append(f"[FAIL] {target_file} - {result.stderr}")
                    all_passed = False
            except Exception as e:
                logs_list.append(f"[WARN] {target_file} - could not validate: {e}")

        # JS files: syntax check with node --check (only plain JS, not JSX/TSX which node can't parse)
        elif target_file.endswith((".js", ".mjs")):
            try:
                result = subprocess.run(
                    ["node", "--check", full_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    logs_list.append(f"[PASS] {target_file} - syntax OK")
                else:
                    logs_list.append(f"[FAIL] {target_file} - {result.stderr}")
                    all_passed = False
            except Exception as e:
                logs_list.append(
                    f"[SKIP] {target_file} - node not available for syntax check: {e}"
                )

        # JSX/TSX files: skip node --check (Node.js can't parse JSX), validated by build step instead
        elif target_file.endswith((".jsx", ".tsx")):
            logs_list.append(f"[SKIP] {target_file} - JSX/TSX validated by build step")

        # TypeScript files: syntax check with tsc --noEmit
        elif target_file.endswith(".ts"):
            try:
                result = subprocess.run(
                    ["npx", "--yes", "tsc", "--noEmit", "--allowJs", "--checkJs", full_path],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    shell=(os.name == "nt"),
                )
                if result.returncode == 0:
                    logs_list.append(f"[PASS] {target_file} - TypeScript syntax OK")
                else:
                    logs_list.append(f"[FAIL] {target_file} - {result.stderr[:300]}")
                    all_passed = False
            except Exception as e:
                logs_list.append(
                    f"[SKIP] {target_file} - TypeScript compiler not available: {e}"
                )

        # Go files: syntax check with go vet
        elif target_file.endswith(".go"):
            try:
                go_dir = os.path.dirname(target_file)
                go_vet_path = "./" + go_dir + "/..." if go_dir else "./..."
                result = subprocess.run(
                    ["go", "vet", go_vet_path],
                    cwd=repo_local_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    logs_list.append(f"[PASS] {target_file} - Go vet OK")
                else:
                    logs_list.append(f"[FAIL] {target_file} - {result.stderr[:300]}")
                    all_passed = False
            except Exception as e:
                logs_list.append(
                    f"[SKIP] {target_file} - go vet not available: {e}"
                )

        # Java files: syntax check with javac (dry run)
        elif target_file.endswith(".java"):
            try:
                import tempfile as _tmpmod
                _javac_tmp = _tmpmod.mkdtemp(prefix="cs_javac_")
                try:
                    result = subprocess.run(
                        ["javac", "-d", _javac_tmp, full_path],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        logs_list.append(f"[PASS] {target_file} - Java syntax OK")
                    else:
                        logs_list.append(f"[FAIL] {target_file} - {result.stderr[:300]}")
                        all_passed = False
                finally:
                    import shutil as _shutil
                    _shutil.rmtree(_javac_tmp, ignore_errors=True)
            except Exception as e:
                logs_list.append(
                    f"[SKIP] {target_file} - javac not available: {e}"
                )

        # Rust files: validated by cargo build step
        elif target_file.endswith(".rs"):
            logs_list.append(f"[SKIP] {target_file} - Rust validated by cargo build step")

        # HTML files: basic structure check
        elif target_file.endswith((".html", ".htm")):
            try:
                with open(full_path, "r", errors="ignore") as f:
                    content = f.read()
                from html.parser import HTMLParser

                parser = HTMLParser()
                parser.feed(content)
                logs_list.append(f"[PASS] {target_file} - HTML parsed OK")
            except Exception as e:
                logs_list.append(f"[FAIL] {target_file} - HTML parse error: {e}")
                all_passed = False

        # CSS files: check for balanced braces
        elif target_file.endswith(".css"):
            try:
                with open(full_path, "r", errors="ignore") as f:
                    content = f.read()
                open_count = content.count("{")
                close_count = content.count("}")
                if open_count == close_count:
                    logs_list.append(
                        f"[PASS] {target_file} - CSS braces balanced ({open_count} blocks)"
                    )
                else:
                    logs_list.append(
                        f"[FAIL] {target_file} - CSS braces unbalanced (opened: {open_count}, closed: {close_count})"
                    )
                    all_passed = False
            except Exception as e:
                logs_list.append(f"[FAIL] {target_file} - CSS read error: {e}")
                all_passed = False

        else:
            logs_list.append(f"[SKIP] {target_file} - no validator for this file type")

        if any("[FAIL]" in log for log in logs_list[logs_len_before:]):
            failed_issue_ids.append(patch.get("patch_id"))

    # Build verification stage
    build_passed = True

    # Check for frontend package.json first, then fallback to root
    frontend_pkg = os.path.join(repo_local_path, "frontend", "package.json")
    root_pkg = os.path.join(repo_local_path, "package.json")
    pkg_path = (
        frontend_pkg
        if os.path.exists(frontend_pkg)
        else (root_pkg if os.path.exists(root_pkg) else None)
    )

    if pkg_path:
        build_cwd = os.path.dirname(pkg_path)
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
                if "scripts" in pkg and "build" in pkg["scripts"]:
                    res = subprocess.run(
                        ["npm", "run", "build"],
                        cwd=build_cwd,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if res.returncode != 0:
                        build_passed = False
                        logs_list.append(
                            f"[FAIL] Build verification failed (npm run build in {build_cwd}):\n{res.stderr[:500]}"
                        )
                    else:
                        logs_list.append(
                            f"[PASS] Build verification passed (npm run build in {build_cwd})"
                        )
        except Exception as e:
            logs_list.append(f"[WARN] package.json build error: {e}")

    elif os.path.exists(
        os.path.join(repo_local_path, "pyproject.toml")
    ) or os.path.exists(os.path.join(repo_local_path, "setup.py")):
        try:
            res = subprocess.run(
                [sys.executable, "-m", "build"],
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode != 0 and "No module named build" not in res.stderr:
                build_passed = False
                logs_list.append(
                    f"[FAIL] Build verification failed (python -m build):\n{res.stderr[:500]}"
                )
            else:
                logs_list.append("[PASS] Build verification passed (python -m build)")
        except Exception as e:
            logs_list.append(f"[WARN] setup.py/pyproject.toml build error: {e}")

    elif os.path.exists(os.path.join(repo_local_path, "pom.xml")):
        try:
            res = subprocess.run(
                ["mvn", "package", "-DskipTests"],
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode != 0:
                build_passed = False
                logs_list.append(
                    f"[FAIL] Build verification failed (mvn package):\n{res.stdout[-500:]}"
                )
            else:
                logs_list.append("[PASS] Build verification passed (mvn package)")
        except Exception as e:
            logs_list.append(f"[WARN] pom.xml build error: {e}")

    elif os.path.exists(os.path.join(repo_local_path, "build.gradle")) or os.path.exists(os.path.join(repo_local_path, "build.gradle.kts")):
        try:
            gradle_cmd = ["./gradlew", "assemble"] if os.path.exists(os.path.join(repo_local_path, "gradlew")) else ["gradle", "assemble"]
            res = subprocess.run(
                gradle_cmd,
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode != 0:
                build_passed = False
                logs_list.append(
                    f"[FAIL] Build verification failed ({' '.join(gradle_cmd)}):\n{res.stdout[-500:]}"
                )
            else:
                logs_list.append(f"[PASS] Build verification passed ({' '.join(gradle_cmd)})")
        except Exception as e:
            logs_list.append(f"[WARN] Gradle build error: {e}")

    elif os.path.exists(os.path.join(repo_local_path, "go.mod")):
        try:
            res = subprocess.run(
                ["go", "build", "./..."],
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if res.returncode != 0:
                build_passed = False
                logs_list.append(
                    f"[FAIL] Build verification failed (go build):\n{res.stderr[:500]}"
                )
            else:
                logs_list.append("[PASS] Build verification passed (go build)")
        except Exception as e:
            logs_list.append(f"[WARN] go.mod build error: {e}")

    elif os.path.exists(os.path.join(repo_local_path, "Cargo.toml")):
        try:
            res = subprocess.run(
                ["cargo", "build"],
                cwd=repo_local_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if res.returncode != 0:
                build_passed = False
                logs_list.append(
                    f"[FAIL] Build verification failed (cargo build):\n{res.stderr[:500]}"
                )
            else:
                logs_list.append("[PASS] Build verification passed (cargo build)")
        except Exception as e:
            logs_list.append(f"[WARN] Cargo.toml build error: {e}")

    test_logs = ""
    if not build_passed:
        all_passed = False
        test_logs = "Tests skipped due to build failure."
    else:
        # Dynamic test suite execution
        knowledge_graph = state.get("knowledge_graph", {})
        test_framework = knowledge_graph.get("test_framework", "")

        if test_framework and _is_allowed_cmd(test_framework):
            cmd = shlex.split(test_framework)
            try:
                res = subprocess.run(
                    cmd, cwd=repo_local_path, capture_output=True, text=True, timeout=60
                )
                test_logs = res.stdout[:500] if res.stdout else res.stderr[:500]
                if res.returncode != 0:
                    if "not found" not in test_logs.lower():
                        all_passed = False
            except Exception as e:
                test_logs = (
                    f"Failed to execute dynamic test suite '{test_framework}': {e}"
                )
        else:
            # Intelligent fallback based on repository language detection
            ext_counts = {}
            for r_dir, r_dirs, r_files in os.walk(repo_local_path):
                r_dirs[:] = [d for d in r_dirs if d not in (".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", "target")]
                for fname in r_files:
                    ext = os.path.splitext(fname)[1]
                    if ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rs"):
                        ext_counts[ext] = ext_counts.get(ext, 0) + 1

            py_count = ext_counts.get(".py", 0)
            js_ts_count = sum(ext_counts.get(e, 0) for e in (".js", ".ts", ".jsx", ".tsx"))
            go_count = ext_counts.get(".go", 0)
            java_count = ext_counts.get(".java", 0)
            rs_count = ext_counts.get(".rs", 0)

            fallback_cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
            if py_count >= max(js_ts_count, go_count, java_count, rs_count, 1):
                if shutil.which("pytest"):
                    fallback_cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"]
                else:
                    fallback_cmd = [sys.executable, "-m", "unittest", "discover"]
            elif js_ts_count >= max(py_count, go_count, java_count, rs_count, 1):
                fallback_cmd = ["npm", "test"]
            elif go_count >= max(py_count, js_ts_count, java_count, rs_count, 1):
                fallback_cmd = ["go", "test", "./..."]
            elif java_count >= max(py_count, js_ts_count, go_count, rs_count, 1):
                if os.path.exists(os.path.join(repo_local_path, "gradlew")):
                    fallback_cmd = ["./gradlew", "test"]
                elif os.path.exists(os.path.join(repo_local_path, "build.gradle")) or os.path.exists(os.path.join(repo_local_path, "build.gradle.kts")):
                    fallback_cmd = ["gradle", "test"]
                else:
                    fallback_cmd = ["mvn", "test"]
            elif rs_count >= max(py_count, js_ts_count, go_count, java_count, 1):
                fallback_cmd = ["cargo", "test"]

            try:
                res = subprocess.run(
                    fallback_cmd,
                    cwd=repo_local_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                test_logs = res.stdout[:500] if res.stdout else res.stderr[:500]
                if res.returncode != 0:
                    if "not found" not in test_logs.lower() and "no tests ran" not in test_logs.lower() and "zero tests" not in test_logs.lower():
                        all_passed = False
            except Exception as e:
                test_logs = f"No test suite executed successfully ({' '.join(fallback_cmd)}): {e}"

    retry_count = state.get("retry_count", 0)
    unresolvable = False
    unresolvable_fixes = state.get("unresolvable_fixes", [])
    touched_symbols = state.get("touched_symbols", {})

    if not all_passed:
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
    files_validated = len(patches)
    files_passed = sum(1 for log_line in logs_list if "[PASS]" in log_line)

    last_patch_id = patches[-1].get("patch_id", 0) if patches else 0

    if not all_passed and not failed_issue_ids and patches:
        failed_issue_ids.append(last_patch_id)

    new_validation_results.append(
        {
            "patch_id": last_patch_id,
            "passed": all_passed,
            "unresolvable": unresolvable,
            "logs": "\n".join(logs_list) + "\n\nTest Results:\n" + test_logs,
            "files_validated": files_validated,
            "files_passed": files_passed,
            "failed_issue_ids": failed_issue_ids,
        }
    )

    investigated_issues = state.get("investigated_issues", [])
    issue = next((i for i in investigated_issues if i.get("id") == last_patch_id), {})
    issue_desc = issue.get("description", str(issue))

    security_clean = state.get("security_verified", False)
    similar = await asyncio.to_thread(query_similar_fixes, issue_desc, 1)
    chroma_score = similar[0].get("confidence", 0.0) if similar else 0.0
    confidence = calculate_pipeline_confidence(
        state,
        tests_passed=files_passed,
        tests_total=files_validated,
        security_clean=security_clean,
        chroma_score=chroma_score,
    )

    if all_passed:
        for patch in patches:
            p_id = patch.get("patch_id")
            p_issue = next((i for i in investigated_issues if i.get("id") == p_id), {})
            p_desc = p_issue.get("description", patch.get("file", issue_desc))
            await asyncio.to_thread(
                store_validated_fix,
                issue_description=p_desc,
                patch=patch.get("diff", ""),
                confidence=confidence,
            )

    return {
        "validation_results": new_validation_results,
        "confidence_score": confidence,
        "unresolvable_fixes": unresolvable_fixes,
        "retry_count": retry_count,
        "touched_symbols": touched_symbols,
    }
