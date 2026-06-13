import json
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
from tools.prompt_cache import REPAIR_PLANNER_SYSTEM

async def agent_repair_planner(state: PipelineState):
    investigated_issues = state.get("investigated_issues", [])
    
    if not investigated_issues or not GROQ_API_KEYS:
        return {"repair_plan": [], "awaiting_approval": False}
    
    # Tier 2 — Repair planning requires deep reasoning about fix ordering
    # and risk classification.
    prompt = f"""{REPAIR_PLANNER_SYSTEM}

Given these investigated issues:
{json.dumps(investigated_issues)}

Create an ordered repair plan. Order matters (e.g. fix auth bypass before fixing API routes).
Classify each fix as "low-risk" or "high-risk". High-risk categories: authentication changes, database schema changes, cryptographic changes.

Return ONLY valid JSON array:
[
  {{"issue_id": 1, "action": "...", "risk": "low-risk" | "high-risk", "reasoning": "..."}}
]"""
    
    try:
        repair_plan = invoke_llm(
            prompt,
            agent_name="repair_planner",
            tier=2,
            expect_json=True,
            json_array=True,
        )
        if not isinstance(repair_plan, list):
            repair_plan = []
    except Exception as e:
        print(f"Error planning repairs: {e}")
        repair_plan = []
        
    # Check if any fix is high-risk to pause pipeline
    awaiting_approval = any(item.get("risk") == "high-risk" for item in repair_plan)
    
    result = {
        "repair_plan": repair_plan,
        "awaiting_approval": awaiting_approval
    }
    
    if not repair_plan and investigated_issues:
        result["pr_error"] = "Failed to generate repair plan: API Rate Limit Exceeded or LLM failure."
        
    return result