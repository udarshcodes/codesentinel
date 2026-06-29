from models.pipeline_state import PipelineState
from tools.analysis_runner import run_semgrep_on_files, run_bandit_on_files
import os


async def agent_security_verifier(state: PipelineState):
    validation_results = state.get("validation_results", [])
    existing_retries = state.get("retry_count", 0)
    if not validation_results or not validation_results[-1].get("passed"):
        # Validation failed — pass through retry_count so orchestrator can track retries
        return {
            "security_verified": False,
            "retry_count": existing_retries,
        }

    patches = state.get("patches", [])
    repo_local_path = state.get("repo_local_path", "")
    original_rules = {
        f.get("rule") for f in state.get("static_findings", []) if f.get("rule")
    }

    # Collect only the files that were modified by patches
    modified_files = list(
        {os.path.join(repo_local_path, p["file"]) for p in patches if p.get("file")}
    )

    if not modified_files:
        return {"security_verified": True}

    new_semgrep = run_semgrep_on_files(modified_files, cwd=repo_local_path or None)
    new_bandit = run_bandit_on_files(modified_files, cwd=repo_local_path or None)

    all_new = []
    for f in new_semgrep:
        all_new.append(f)
    for f in new_bandit:
        all_new.append(f)

    # Check if any original vulnerability rules still fire
    still_vulnerable = [
        f
        for f in all_new
        if f.get("check_id") in original_rules or f.get("test_id") in original_rules
    ]

    if still_vulnerable:
        return {
            "security_verified": False,
            "security_retry_context": still_vulnerable,
            "retry_count": existing_retries + 1,
        }

    return {"security_verified": True}
