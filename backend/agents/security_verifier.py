from models.pipeline_state import PipelineState
from agents.static_analysis import agent_static_analysis
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
    
    # Track BOTH rule and tool so we don't drop issues from tools that don't emit a strict rule ID
    original_rules = {
        f.get("rule") or f.get("tool") for f in state.get("static_findings", []) if f.get("rule") or f.get("tool")
    }

    # Collect only the files that were modified by patches
    modified_files = {
        os.path.normpath(os.path.join(repo_local_path, p["file"]))
        for p in patches if p.get("file")
    }

    if not modified_files:
        return {"security_verified": True}

    # Re-run full static analysis to get all findings across all supported languages
    # This prevents the unwired issue where JS/Go/Rust fixes were blindly passed
    new_analysis_state = dict(state)
    new_analysis_result = await agent_static_analysis(new_analysis_state)
    new_findings = new_analysis_result.get("static_findings", [])

    still_vulnerable = []

    for finding in new_findings:
        f_path = finding.get("file", "")
        abs_path = os.path.normpath(os.path.join(repo_local_path, f_path))
        
        # Only verify if the vulnerability is in a file we actually modified
        if abs_path in modified_files:
            f_rule = finding.get("rule")
            f_tool = finding.get("tool")
            
            identifier = f_rule if f_rule else f_tool
            if identifier in original_rules:
                still_vulnerable.append(finding)

    if still_vulnerable:
        return {
            "security_verified": False,
            "security_retry_context": still_vulnerable,
            "retry_count": existing_retries + 1,
        }

    return {"security_verified": True}
