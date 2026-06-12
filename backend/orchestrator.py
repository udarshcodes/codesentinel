import asyncio
from langgraph.graph import StateGraph, END
from models.pipeline_state import PipelineState
from agents.repo_mapper import agent_repo_mapper
from agents.dependency_analyzer import agent_dependency_analyzer
from agents.static_analysis import agent_static_analysis
from agents.bug_investigator import agent_bug_investigator
from agents.repair_planner import agent_repair_planner
from agents.code_generator import agent_code_generator
from agents.validator import agent_validator
from agents.security_verifier import agent_security_verifier
from agents.pr_author import agent_pr_author

# --- Graph Definition ---

workflow = StateGraph(PipelineState)

# Add nodes
workflow.add_node("repo_mapper", agent_repo_mapper)
workflow.add_node("dependency_analyzer", agent_dependency_analyzer)
workflow.add_node("static_analysis", agent_static_analysis)
workflow.add_node("bug_investigator", agent_bug_investigator)
workflow.add_node("repair_planner", agent_repair_planner)
workflow.add_node("code_generator", agent_code_generator)
