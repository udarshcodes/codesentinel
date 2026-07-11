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

# --- Agent 10: Orchestrator Agent ---
# The Orchestrator is an intelligent meta-agent that controls the pipeline.
# It makes dynamic decisions at conditional edges using heuristics and
# logs its reasoning for observability.


class OrchestratorAgent:
    """
    Intelligent orchestrator that controls what runs next, what retries,
    and what fails. Implements the 'Agent 10 — Orchestrator Agent' from
    the specification.
    """

    @staticmethod
    def route_after_validator(state: PipelineState) -> str:
        """Decide whether to retry code generation or proceed to security verification."""
        if state.get("approval_decision") == "rejected":
            print("[Orchestrator] Repair plan was REJECTED — proceeding to PR author.")
            return "pr_author"

        validation_results = state.get("validation_results", [])
        retry_count = state.get("retry_count", 0)
        patches = state.get("patches", [])

        if not validation_results:
            print(
                "[Orchestrator] No validation results — proceeding to security verification."
            )
            return "security_verifier"

        latest = validation_results[-1]

        if latest.get("passed") and not latest.get("build_failed") and not latest.get("suite_failed"):
            print(
                "[Orchestrator] Validation PASSED — proceeding to security verification."
            )
            return "security_verifier"

        if latest.get("unresolvable") or retry_count >= 3:
            print(
                f"[Orchestrator] Validation FAILED after {retry_count} retries — "
                f"marking as unresolvable and proceeding to security verification."
            )
            return "security_verifier"

        # Check if there are any applied patches worth retrying
        applied_patches = [p for p in patches if p.get("applied")]
        if not applied_patches:
            print(
                "[Orchestrator] No patches were successfully applied — skipping retry, "
                "proceeding to security verification."
            )
            return "security_verifier"

        files_passed = latest.get("files_passed", 0)
        files_validated = latest.get("files_validated", 1)
        pass_ratio = files_passed / max(files_validated, 1)

        print(
            f"[Orchestrator] Validation FAILED (pass ratio: {pass_ratio:.0%}, "
            f"retry {retry_count}/3) — routing back to code_generator for retry."
        )
        return "code_generator"

    @staticmethod
    def route_after_security(state: PipelineState) -> str:
        """Decide whether to retry after security verification failure or proceed to PR."""
        if state.get("approval_decision") == "rejected":
            print("[Orchestrator] Repair plan was REJECTED — proceeding to PR author.")
            return "pr_author"

        security_verified = state.get("security_verified")
        retry_count = state.get("retry_count", 0)
        security_retry_context = state.get("security_retry_context", [])

        if security_verified:
            print(
                "[Orchestrator] Security verification PASSED — proceeding to PR author."
            )
            return "pr_author"

        if retry_count >= 3:
            remaining_vulns = len(security_retry_context)
            print(
                f"[Orchestrator] Security verification FAILED after {retry_count} retries "
                f"({remaining_vulns} vulnerabilities remain) — proceeding to PR author anyway."
            )
            return "pr_author"

        remaining_vulns = len(security_retry_context)
        print(
            f"[Orchestrator] Security verification FAILED ({remaining_vulns} vulnerabilities "
            f"still present, retry {retry_count}/3) — routing back to code_generator."
        )
        return "code_generator"


orchestrator = OrchestratorAgent()

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

# Edges (sequential pipeline with conditional cycles for validation and security retries)
workflow.set_entry_point("repo_mapper")
workflow.add_edge("repo_mapper", "dependency_analyzer")
workflow.add_edge("dependency_analyzer", "static_analysis")
workflow.add_edge("static_analysis", "bug_investigator")
workflow.add_edge("bug_investigator", "repair_planner")
workflow.add_edge("repair_planner", "code_generator")
workflow.add_edge("code_generator", "validator")

# Orchestrator-controlled conditional routing
workflow.add_conditional_edges(
    "validator",
    orchestrator.route_after_validator,
    {
        "security_verifier": "security_verifier",
        "code_generator": "code_generator",
        "pr_author": "pr_author",
    },
)

workflow.add_conditional_edges(
    "security_verifier",
    orchestrator.route_after_security,
    {"pr_author": "pr_author", "code_generator": "code_generator"},
)

workflow.add_edge("pr_author", END)

# Compile the graph
app = workflow.compile()
