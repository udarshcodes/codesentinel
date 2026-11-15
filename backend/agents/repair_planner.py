import json
import asyncio
from datetime import datetime, timezone
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
from tools.prompt_cache import REPAIR_PLANNER_SYSTEM


async def agent_repair_planner(state: PipelineState):
    import copy
    investigated_issues = copy.deepcopy(state.get("investigated_issues", []))
    advisory_only = {"dead_code_detector", "dead_file_checker", "css_quality_checker"}
    investigated_issues = [issue for issue in investigated_issues if issue.get("remediation_mode") != "manual_review" and issue.get("original_finding", {}).get("tool") not in advisory_only]

    if not investigated_issues:
        return {"repair_plan": [], "awaiting_approval": False, "pr_error": "No automatic repairs selected; advisory findings require manual review."}
    if not GROQ_API_KEYS:
        return {"repair_plan": [], "awaiting_approval": False, "pr_error": "No configured LLM credentials are available for repair planning."}

    # Prevent massive payloads from mangling the LLM prompt
    while (
        len(json.dumps(investigated_issues)) > 12000 and len(investigated_issues) > 10
    ):
        investigated_issues.pop()

    # Check if all issues are just dependency updates
    all_dependency = all(
        "dependency" in str(issue.get("description") or issue.get("issue", "")).lower() or bool(issue.get("original_finding", {}).get("package"))
        for issue in investigated_issues
    )
    
    if all_dependency:
        repair_plan = [{
            "issue_id": issue["id"],
            "proposed_action": "Repair this dependency finding using a compatible supported version; synchronize the lockfile and validate the resulting build/tests.",
            "risk_level": "low-risk",
            "reasoning": "Dependency changes require compatibility and vulnerability checks, not just a latest-version substitution.",
            "issue_summary": issue.get("description") or issue.get("issue", "Dependency finding")
        } for issue in investigated_issues if "id" in issue]
    else:
        # Tier 2 — Repair planning requires deep reasoning about fix ordering
        # and risk classification.
        prompt = f"""{REPAIR_PLANNER_SYSTEM}

Given these investigated issues:
{json.dumps(investigated_issues)}

Propose only actionable repairs with a concrete behavior or security benefit. Do not change tests to silence scanners, replace pytest asserts, or add comment-only fixes. Report cosmetic findings for manual review. Create an ordered repair plan. Order matters (e.g. fix auth bypass before fixing API routes).
Classify each fix as "low-risk" or "high-risk". High-risk categories: authentication changes, database schema changes, cryptographic changes.

Return ONLY valid JSON array:
[
  {{"issue_id": 1, "issue_summary": "...", "proposed_action": "...", "risk_level": "low-risk" | "high-risk", "reasoning": "..."}}
]"""

        try:
            repair_plan = await invoke_llm(
                prompt,
                agent_name="repair_planner",
                task_class="DEEP",
                expect_json=True,
                json_array=True,
            )
            if not isinstance(repair_plan, list):
                repair_plan = []
        except Exception as e:
            from tools.llm_router import LLMExhaustionError
            if isinstance(e, LLMExhaustionError):
                raise
            print(f"Error planning repairs: {e}")
            repair_plan = []

    # Never let model-generated identifiers select unrelated or nonexistent issues.
    issues_by_id = {str(issue.get("id")): issue for issue in investigated_issues if "id" in issue}
    repair_plan = [fix for fix in repair_plan if isinstance(fix, dict) and str(fix.get("issue_id")) in issues_by_id]
    advisory_only = {"dead_code_detector", "dead_file_checker", "css_quality_checker"}
    repair_plan = [fix for fix in repair_plan if issues_by_id[str(fix["issue_id"])].get("original_finding", {}).get("tool") not in advisory_only]
    for fix in repair_plan:
        fix["issue_id"] = issues_by_id[str(fix["issue_id"])]["id"]
        finding = issues_by_id[str(fix["issue_id"])].get("original_finding", {})
        if finding.get("ecosystem") == "npm" and finding.get("recommended_version"):
            fix["proposed_action"] = (f"Update {finding['package']} from {finding.get('current_version')} to the registry-confirmed "
                                      f"same-major release {finding['recommended_version']}; its OSV candidate scan found no advisories. "
                                      "Synchronize the npm lock, verify peer dependencies, build, lint and rescan. Do not downgrade or invent versions.")
    planned = {str(fix["issue_id"]) for fix in repair_plan}
    for issue in state.get("investigated_issues", []):
        if issue.get("original_finding", {}).get("rule") == "B113" and str(issue.get("id")) not in planned:
            repair_plan.insert(0, {"issue_id": issue["id"], "issue_summary": "HTTP request has no finite timeout",
                                   "proposed_action": "Add a finite request timeout while preserving other request arguments.",
                                   "risk_level": "low-risk", "reasoning": "Bounded request waiting; no credential or schema change."})

    HIGH_RISK_KEYWORDS = [
        "jwt",
        "token",
        "auth",
        "password",
        "secret",
        "crypto",
        "encrypt",
        "schema",
        "migration",
        "database",
        "drop table",
        "alter table",
    ]

    def classify_risk(fix: dict) -> str:
        description = (
            str(fix.get("issue_summary", ""))
            + str(fix.get("reasoning", ""))
            + str(fix.get("proposed_action", ""))
        ).lower()
        for kw in HIGH_RISK_KEYWORDS:
            if kw in description:
                return "high-risk"
        return "low-risk"

    import hashlib
    for fix in repair_plan:
        if fix.get("risk_level") != "high-risk":
            fix["risk_level"] = classify_risk(fix)
            
        fix["issue_id"] = fix.get("issue_id", "unknown")
        fix["issue_summary"] = fix.get("issue_summary", "")
        fix["proposed_action"] = fix.get("proposed_action", "")
        fix["reasoning"] = fix.get("reasoning", "")
        fix["status"] = fix.get("status", "pending")
        
        if "id" in fix and "fix_id" not in fix:
            fix["fix_id"] = str(fix.pop("id"))
        elif "id" in fix:
            fix.pop("id")
            
        if "fix_id" not in fix:
            unique_str = f"{fix.get('issue_id')}-{fix.get('proposed_action')}-{fix.get('issue_summary')}"
            fix["fix_id"] = hashlib.sha256(unique_str.encode()).hexdigest()[:12]

    # Check if any fix is high-risk to pause pipeline
    awaiting_approval = any(item.get("risk_level") == "high-risk" for item in repair_plan)
    task_id = state.get("task_id", "")

    if awaiting_approval and task_id:
        # The state persistence and waiting_for_approval event is now handled atomically by worker.py
        # We just need to return the state telling the worker to wait.
        return {
            "repair_plan": repair_plan,
            "awaiting_approval": True,
            "approval_decision": None
        }

    result = {"repair_plan": repair_plan, "awaiting_approval": False}

    if not repair_plan and investigated_issues:
        result["pr_error"] = (
            "Failed to generate repair plan: API Rate Limit Exceeded or LLM failure."
        )

    return result
