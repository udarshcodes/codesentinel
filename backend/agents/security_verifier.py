from models.pipeline_state import PipelineState
from agents.static_analysis import agent_static_analysis
import os
from tools.safe_repo import safe_walk, safe_read_text, safe_path_exists, open_safe


async def agent_security_verifier(state: PipelineState):
    validation_results = state.get("validation_results", [])
    # We use a separate security_retry_count so we don't share retry limits with validation
    existing_retries = state.get("security_retry_count", state.get("retry_count", 0))
    
    if not validation_results or not validation_results[-1].get("passed"):
        # Validation failed — pass through so orchestrator can track retries
        return {
            "security_verified": False,
            "security_retry_count": existing_retries,
        }

    patches = state.get("patches", [])
    repo_local_path = state.get("repo_local_path", "")
    original_findings = state.get("static_findings", [])

    {
        f.get("rule") or f.get("tool")
        for f in original_findings
        if f.get("rule") or f.get("tool")
    }

    modified_files = {
        os.path.normpath(os.path.join(repo_local_path, p["file"]))
        for p in patches
        if p.get("file")
    }

    if not modified_files:
        return {"security_verified": True}

    # Re-run full static analysis to get all findings
    new_analysis_state = dict(state)
    new_analysis_result = await agent_static_analysis(new_analysis_state)
    new_findings = new_analysis_result.get("static_findings", [])
    
    # If the static analysis explicitly reports that scanners crashed or timed out
    # we treat it as a verification failure, preventing a false positive of 0 findings.
    if new_analysis_result.get("scanners_failed", False):
        return {
            "security_verified": False,
            "security_retry_context": [{"issue": "Security scanners crashed or timed out during verification. Fix the code to avoid breaking the scanners."}],
            "security_retry_count": existing_retries + 1,
        }

    still_vulnerable = []

    for finding in new_findings:
        f_path = finding.get("file", "")
        abs_path = os.path.normpath(os.path.join(repo_local_path, f_path))

        # Only verify if the vulnerability is in a file we actually modified
        if abs_path in modified_files:
            finding.get("rule")
            finding.get("tool")

            
            # Rule 1: The original vulnerabilities remain in the modified files.
            # Rule 2: NEW vulnerabilities were introduced in the modified files.
            # Both cases mean the code is still vulnerable / worse.
            
            # We add all findings in modified files to the retry context
            still_vulnerable.append(finding)

    if still_vulnerable:
        return {
            "security_verified": False,
            "security_retry_context": still_vulnerable,
            "security_retry_count": existing_retries + 1,
        }

    return {"security_verified": True}
