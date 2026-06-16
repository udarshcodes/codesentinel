import json
import asyncio
from models.pipeline_state import PipelineState
from state import approval_events, broadcast_sse
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
from tools.prompt_cache import REPAIR_PLANNER_SYSTEM

async def agent_repair_planner(state: PipelineState):
    investigated_issues = state.get("investigated_issues", [])
    
    if not investigated_issues or not GROQ_API_KEYS:
        return {"repair_plan": [], "awaiting_approval": False}
        
    # Prevent massive payloads from mangling the LLM prompt
    while len(json.dumps(investigated_issues)) > 12000 and len(investigated_issues) > 10:
        investigated_issues.pop()
    
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
        
    HIGH_RISK_KEYWORDS = [
        'jwt', 'token', 'auth', 'password', 'secret', 'crypto', 'encrypt',
        'schema', 'migration', 'database', 'drop table', 'alter table'
    ]

    def classify_risk(fix: dict) -> str:
        description = (fix.get('description', '') + fix.get('files_to_change', '') + fix.get('reasoning', '') + fix.get('action', '')).lower()
        for kw in HIGH_RISK_KEYWORDS:
            if kw in description:
                return 'high-risk'
        return 'low-risk'
        
    for fix in repair_plan:
        if fix.get('risk') != 'high-risk':
            fix['risk'] = classify_risk(fix)
            
    # Check if any fix is high-risk to pause pipeline
    awaiting_approval = any(item.get("risk") == "high-risk" for item in repair_plan)
    task_id = state.get("task_id", "")
    
    if awaiting_approval and task_id:
        event = asyncio.Event()
        approval_events[task_id] = {'event': event, 'decision': None}
        
        await broadcast_sse(task_id, {
            'event': 'approval_required',
            'data': {
                'agent': 'repair_planner',
                'fix': repair_plan
            }
        })
        
        await event.wait()
        decision = approval_events.pop(task_id).get('decision')
        
        return {
            "repair_plan": repair_plan,
            "awaiting_approval": False, # Consumed
            "approval_decision": decision
        }
    
    result = {
        "repair_plan": repair_plan,
        "awaiting_approval": awaiting_approval
    }
    
    if not repair_plan and investigated_issues:
        result["pr_error"] = "Failed to generate repair plan: API Rate Limit Exceeded or LLM failure."
        
    return result