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

    if not investigated_issues or not GROQ_API_KEYS:
        return {"repair_plan": [], "awaiting_approval": False}

    # Prevent massive payloads from mangling the LLM prompt
    while (
        len(json.dumps(investigated_issues)) > 12000 and len(investigated_issues) > 10
    ):
        investigated_issues.pop()

    # Check if all issues are just dependency updates
    all_dependency = all(
        "dependency" in str(issue.get("issue", "")).lower()
        for issue in investigated_issues
    )
    
    if all_dependency:
        repair_plan = [{
            "issue_id": 1, 
            "proposed_action": "Update vulnerable dependencies to their latest secure versions.", 
            "risk_level": "low-risk", 
            "reasoning": "Standard dependency update.",
            "issue_summary": "Vulnerable dependencies found."
        }]
    else:
        # Tier 2 — Repair planning requires deep reasoning about fix ordering
        # and risk classification.
        prompt = f"""{REPAIR_PLANNER_SYSTEM}

Given these investigated issues:
{json.dumps(investigated_issues)}

Create an ordered repair plan. Order matters (e.g. fix auth bypass before fixing API routes).
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
