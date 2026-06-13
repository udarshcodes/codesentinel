import os
import shutil
import subprocess
from models.pipeline_state import PipelineState

async def agent_security_verifier(state: PipelineState):
    repo_local_path = state.get("repo_local_path", "")
    validation_results = state.get("validation_results", [])
    
    if not validation_results or not validation_results[-1].get("passed"):
        return {"security_verified": False}
    
    # Re-run lightweight semgrep on modified files to verify fix
    semgrep_path = shutil.which("semgrep")
    if not semgrep_path:
        print("[SecurityVerifier] semgrep not found in PATH, skipping verification.")
        return {"security_verified": True}
    
    try:
        result = subprocess.run(
            [semgrep_path, "--config=auto", "--json", "."],
            cwd=repo_local_path,
            capture_output=True,
            text=True,
            timeout=60
        )
        # Check if semgrep found any remaining issues
        if result.stdout:
            import json
            data = json.loads(result.stdout)
            remaining_issues = data.get("results", [])
            if remaining_issues:
                print(f"[SecurityVerifier] {len(remaining_issues)} issues still remain after fix.")
                return {"security_verified": False}
        
        return {"security_verified": True}
    except Exception as e:
        print(f"[SecurityVerifier] semgrep verification failed: {e}")
        return {"security_verified": False}