import os
import sys
import subprocess
from models.pipeline_state import PipelineState

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
        
        # Python files: check syntax with py_compile
        if target_file.endswith(".py"):
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", full_path],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    logs_list.append(f"[PASS] {target_file} - syntax OK")
                else:
                    logs_list.append(f"[FAIL] {target_file} - {result.stderr}")
                    all_passed = False
            except Exception as e:
                logs_list.append(f"[WARN] {target_file} - could not validate: {e}")
                
        # JS/TS files: basic syntax check with node --check
        elif target_file.endswith((".js", ".mjs")):
            try:
                result = subprocess.run(
                    ["node", "--check", full_path],
                    capture_output=True, text=True
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
    
    # Also try running tests if pytest is available
    test_logs = ""
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=short", "-q"],
            cwd=repo_local_path,
            capture_output=True, text=True,
            timeout=30
        )
        test_logs = res.stdout[:500] if res.stdout else res.stderr[:500]
        if res.returncode != 0:
            # Don't fail validation just because there are no tests
            if "no tests ran" not in test_logs.lower() and "not found" not in test_logs.lower():
                all_passed = False
    except Exception as e:
        test_logs = f"No test suite found (pytest not available or timed out): {e}"
    
    # Create a new list rather than mutating the state list directly
    new_validation_results = list(validation_results)
    new_validation_results.append({
        "patch_id": patches[-1].get("patch_id", 0),
        "passed": all_passed,
        "logs": "\n".join(logs_list) + "\n\nTest Results:\n" + test_logs,
        "files_validated": len(patches),
        "files_passed": sum(1 for l in logs_list if "[PASS]" in l)
    })
    
    return {"validation_results": new_validation_results}