import asyncio
from langgraph.graph import StateGraph, END
from models.pipeline_state import PipelineState
from state import approval_events, sse_queues, broadcast_sse

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
workflow.add_node("validator", agent_validator)
workflow.add_node("security_verifier", agent_security_verifier)
workflow.add_node("pr_author", agent_pr_author)

# Edges (Linear for now, conditional handled via pause in SSE layer)
workflow.set_entry_point("repo_mapper")
workflow.add_edge("repo_mapper", "dependency_analyzer")
workflow.add_edge("dependency_analyzer", "static_analysis")
workflow.add_edge("static_analysis", "bug_investigator")
workflow.add_edge("bug_investigator", "repair_planner")
workflow.add_edge("repair_planner", "code_generator")
workflow.add_edge("code_generator", "validator")

def route_after_validator(state: PipelineState) -> str:
    validation_results = state.get('validation_results', [])
    if validation_results and not validation_results[-1].get('passed'):
        if state.get('retry_count', 0) >= 3:
            return 'security_verifier'
        return 'code_generator'
    return 'security_verifier'

workflow.add_conditional_edges("validator", route_after_validator, 
    {"security_verifier": "security_verifier", "code_generator": "code_generator"})

def route_after_security(state: PipelineState) -> str:
    if state.get('security_verified'):
        return 'pr_author'
    if state.get('retry_count', 0) >= 3:
        return 'pr_author' # Skip after max retries
    return 'code_generator' # Loop back

workflow.add_conditional_edges('security_verifier', route_after_security,
    {'pr_author': 'pr_author', 'code_generator': 'code_generator'})
    
workflow.add_edge("pr_author", END)

# Compile the graph
app = workflow.compile()