from typing import TypedDict

class PipelineState(TypedDict, total=False):
    repo_url: str
    repo_local_path: str
    knowledge_graph: dict
    dependency_findings: list
    static_findings: list
    investigated_issues: list
    repair_plan: list
    patches: list
    validation_results: list
    security_verified: bool
    pr_url: str
    pr_error: str
    retry_count: int
    awaiting_approval: bool
    confidence_score: float
    token_usage: dict