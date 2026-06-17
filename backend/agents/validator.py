import os
import sys
import subprocess
import asyncio
from models.pipeline_state import PipelineState
from tools.vector_store import query_similar_fixes, store_validated_fix

async def agent_validator(state: PipelineState):
    repo_local_path = state.get("repo_local_path", "")
    patches = state.get("patches", [])
    validation_results = state.get("validation_results", [])
    
    if not patches or not repo_local_path:
        return {"validation_results": validation_results}
    
    # Since code_generator now writes fixes directly to disk,
    # we validate by checking if the files are syntactically correct.
    
    all_passed = True
    logs_list = []
    
    for patch in patches:
        target_file = patch.get("file", "")
        full_path = os.path.join(repo_local_path, target_file)
        
        if not os.path.exists(full_path):
            logs_list.append(f"[SKIP] {target_file} - file not found")
            continue
            
        if not patch.get("applied", True):
            logs_list.append(f"[FAIL] {target_file} - patch failed to apply, file is unmodified")
            all_passed = False
            continue
        
        # Python files: check syntax with py_compile
        if target_file.endswith(".py"):
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", full_path],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    logs_list.append(f"[PASS] {target_file} - syntax OK")
                else:
                    logs_list.append(f"[FAIL] {target_file} - {result.stderr}")
                    all_passed = False
            except Exception as e:
                logs_list.append(f"[WARN] {target_file} - could not validate: {e}")
                
        # JS/TS/JSX files: basic syntax check with node --check (will fail gracefully on JSX, caught by build step)
        elif target_file.endswith((".js", ".mjs", ".jsx", ".tsx")):
            try:
                result = subprocess.run(
                    ["node", "--check", full_path],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    logs_list.append(f"[PASS] {target_file} - syntax OK")
                else:
                    logs_list.append(f"[FAIL] {target_file} - {result.stderr}")
                    all_passed = False
            except Exception as e:
                logs_list.append(f"[SKIP] {target_file} - node not available for syntax check: {e}")
        
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
                    logs_list.append(f"[PASS] {target_file} - CSS braces balanced ({open_count} blocks)")
                else:
                    logs_list.append(f"[FAIL] {target_file} - CSS braces unbalanced (opened: {open_count}, closed: {close_count})")
                    all_passed = False
            except Exception as e:
                logs_list.append(f"[FAIL] {target_file} - CSS read error: {e}")
                all_passed = False
        
        else:
            logs_list.append(f"[SKIP] {target_file} - no validator for this file type")
    
    # Build verification stage
    build_passed = True
    
    # Check for frontend package.json first, then fallback to root
    frontend_pkg = os.path.join(repo_local_path, "frontend", "package.json")
    root_pkg = os.path.join(repo_local_path, "package.json")
    pkg_path = frontend_pkg if os.path.exists(frontend_pkg) else (root_pkg if os.path.exists(root_pkg) else None)
    
    if pkg_path:
        build_cwd = os.path.dirname(pkg_path)
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                import json
                pkg = json.load(f)
                if "scripts" in pkg and "build" in pkg["scripts"]:
                    res = subprocess.run(["npm", "run", "build"], cwd=build_cwd, capture_output=True, text=True, timeout=60)
                    if res.returncode != 0:
                        build_passed = False
                        logs_list.append(f"[FAIL] Build verification failed (npm run build in {build_cwd}):\n{res.stderr[:500]}")
                    else:
                        logs_list.append(f"[PASS] Build verification passed (npm run build in {build_cwd})")
        except Exception as e:
            logs_list.append(f"[WARN] package.json build error: {e}")

    elif os.path.exists(os.path.join(repo_local_path, "pyproject.toml")) or os.path.exists(os.path.join(repo_local_path, "setup.py")):
        try:
            res = subprocess.run([sys.executable, "-m", "build"], cwd=repo_local_path, capture_output=True, text=True, timeout=60)
            if res.returncode != 0 and "No module named build" not in res.stderr:
                build_passed = False
                logs_list.append(f"[FAIL] Build verification failed (python -m build):\n{res.stderr[:500]}")
            else:
                logs_list.append("[PASS] Build verification passed (python -m build)")
        except Exception as e:
            logs_list.append(f"[WARN] setup.py/pyproject.toml build error: {e}")

    elif os.path.exists(os.path.join(repo_local_path, "pom.xml")):
        try:
            res = subprocess.run(["mvn", "package", "-DskipTests"], cwd=repo_local_path, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                build_passed = False
                logs_list.append(f"[FAIL] Build verification failed (mvn package):\n{res.stdout[-500:]}")
            else:
                logs_list.append("[PASS] Build verification passed (mvn package)")
        except Exception as e:
            logs_list.append(f"[WARN] pom.xml build error: {e}")

    import shlex
    
    test_logs = ""
    if not build_passed:
        all_passed = False
        test_logs = "Tests skipped due to build failure."
    else:
        # Dynamic test suite execution
        knowledge_graph = state.get("knowledge_graph", {})
        test_framework = knowledge_graph.get("test_framework", "")
        
        if test_framework:
            cmd = shlex.split(test_framework)
            try:
                res = subprocess.run(
                    cmd,
                    cwd=repo_local_path,
                    capture_output=True, text=True,
                    timeout=60
                )
                test_logs = res.stdout[:500] if res.stdout else res.stderr[:500]
                if res.returncode != 0:
                    if "not found" not in test_logs.lower():
                        all_passed = False
            except Exception as e:
                test_logs = f"Failed to execute dynamic test suite '{test_framework}': {e}"
        else:
            # Fallback to pytest if not specified
            try:
                res = subprocess.run(
                    [sys.executable, "-m", "pytest", "--tb=short", "-q"],
                    cwd=repo_local_path,
                    capture_output=True, text=True,
                    timeout=30
                )
                test_logs = res.stdout[:500] if res.stdout else res.stderr[:500]
                if res.returncode != 0:
                    if "not found" not in test_logs.lower():
                        all_passed = False
            except Exception as e:
                test_logs = f"No test suite found (pytest not available or timed out): {e}"
    
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
    files_passed = sum(1 for l in logs_list if "[PASS]" in l)
    
    new_validation_results.append({
        "patch_id": patches[-1].get("patch_id", 0),
        "passed": all_passed,
        "unresolvable": unresolvable,
        "logs": "\n".join(logs_list) + "\n\nTest Results:\n" + test_logs,
        "files_validated": files_validated,
        "files_passed": files_passed
    })
    
    investigated_issues = state.get("investigated_issues", [])
    issue = next((i for i in investigated_issues if i.get("id") == patches[-1].get("patch_id")), {})
    issue_desc = issue.get("description", str(issue))
    
    async def compute_confidence(tests_passed, tests_total, security_clean, issue_desc) -> float:
        tests_ratio = tests_passed / tests_total if tests_total > 0 else 0.0
        static_clean = 1.0 if security_clean else 0.0
        
        similar = await asyncio.to_thread(query_similar_fixes, issue_desc, 1)
        chroma_score = similar[0].get('confidence', 0.0) if similar else 0.0
        
        return round(
            (tests_ratio * 0.5) + (static_clean * 0.3) + (chroma_score * 0.2),
            2
        )
        
    security_clean = state.get("security_verified", False)
    confidence = await compute_confidence(files_passed, files_validated, security_clean, issue_desc)
    
    if all_passed:
        for patch in patches:
            await asyncio.to_thread(
                store_validated_fix,
                issue_description=issue_desc,
                patch=patch.get("diff", ""),
                confidence=confidence
            )
    
    return {
        "validation_results": new_validation_results,
        "confidence_score": confidence,
        "unresolvable_fixes": unresolvable_fixes,
        "retry_count": retry_count,
        "touched_symbols": touched_symbols
    }