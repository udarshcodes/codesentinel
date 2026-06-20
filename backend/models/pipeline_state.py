from typing_extensions import TypedDict, NotRequired


class PipelineState(TypedDict, total=False):
    repo_url: str
    commit_sha: NotRequired[str]
    repo_local_path: NotRequired[str]
    knowledge_graph: dict
    dependency_findings: list
    static_findings: list
    investigated_issues: list
    repair_plan: list
    patches: list
    validation_results: list
    security_verified: bool
    pr_url: NotRequired[str]
    retry_count: int
    awaiting_approval: bool
    confidence_score: float
    security_retry_context: NotRequired[dict]
    unresolvable_fixes: NotRequired[list]
    approval_payload: NotRequired[dict]
    approval_decision: NotRequired[str]
    pr_error: NotRequired[str]
    task_id: NotRequired[str]
    touched_symbols: NotRequired[dict]