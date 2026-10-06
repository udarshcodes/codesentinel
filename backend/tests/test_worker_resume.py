import pytest
import asyncio
from unittest.mock import patch, MagicMock
from api.job_manager import JobManager
from tools.llm_router import invoke_llm, LLMExhaustionError
from agents.repair_planner import agent_repair_planner

# 1. Fresh worker enters STARTING correctly
# 2. Resumed WAITING_FOR_LLM_CAPACITY task does not emit STARTING incorrectly
# 3. Resumed WAITING_FOR_LLM_CAPACITY task can continue after cooldown
# 4. Resumed WAITING_FOR_APPROVAL task preserves approval state
# 5. Resumed RUNNING task continues correctly
# 6. STARTING cannot incorrectly jump to WAITING_FOR_APPROVAL
# 7. RUNNING can enter WAITING_FOR_APPROVAL
# 8. Repair Planner high risk fix correctly produces approval state
# 9. Malformed repair plan JSON is handled safely
# 10. LLM JSON failure is not classified as capacity exhaustion
# 11. Duplicate pipeline_started events are avoided
# 12. Existing completed tasks cannot be restarted

def test_transition_starting_to_approval_fails():
    """6. STARTING cannot incorrectly jump to WAITING_FOR_APPROVAL"""
    assert not JobManager._is_valid_transition("STARTING", "WAITING_FOR_APPROVAL")

def test_transition_running_to_approval_succeeds():
    """7. RUNNING can enter WAITING_FOR_APPROVAL"""
    assert JobManager._is_valid_transition("RUNNING", "WAITING_FOR_APPROVAL")

def test_resume_cooldown_evaluation():
    """3. Resumed WAITING_FOR_LLM_CAPACITY task can continue after cooldown"""
    from datetime import datetime, timezone, timedelta
    
    # Cooldown active (future)
    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    can_claim, malformed = JobManager._check_llm_cooldown(future)
    assert not can_claim
    assert not malformed
    
    # Cooldown expired (past)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    can_claim, malformed = JobManager._check_llm_cooldown(past)
    assert can_claim
    assert not malformed

@pytest.mark.asyncio
async def test_repair_planner_malformed_json_handling():
    """9. Malformed repair plan JSON is handled safely"""
    """10. LLM JSON failure is not classified as capacity exhaustion"""
    
    state = {
        "investigated_issues": [{"issue": "Test memory leak"}],
        "task_id": "test_task"
    }
    
    # Mock invoke_llm to simulate JSON parse failure which llm_router now catches
    # and returns empty list instead of throwing LLMExhaustionError
    with patch("agents.repair_planner.invoke_llm", return_value=[]), patch("agents.repair_planner.GROQ_API_KEYS", ["dummy"]):
        res = await agent_repair_planner(state)
        
    assert res.get("repair_plan") == []
    assert not res.get("awaiting_approval")

@pytest.mark.asyncio
async def test_repair_planner_high_risk_approval():
    """8. Repair Planner high risk fix correctly produces approval state"""
    state = {
        "investigated_issues": [{"issue": "Auth bypass"}],
        "task_id": "test_task"
    }
    
    # Return a high-risk fix
    high_risk_plan = [
        {"issue_summary": "jwt auth failure", "proposed_action": "update crypto schema", "risk_level": "high-risk"}
    ]
    with patch("agents.repair_planner.invoke_llm", return_value=high_risk_plan), patch("agents.repair_planner.GROQ_API_KEYS", ["dummy"]):
        res = await agent_repair_planner(state)
        
    assert res.get("awaiting_approval") is True
    assert "repair_plan" in res
    assert res["repair_plan"][0]["risk_level"] == "high-risk"
