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
    
    # State tracking
    status: NotRequired[str]
    current_stage: NotRequired[str]
    current_agent: NotRequired[str]
    last_error: NotRequired[str]
    
    # Validation & PR states
    validation_state: NotRequired[str]
    security_state: NotRequired[str]
    pr_state: NotRequired[str]
    
    # Approval fields
    awaiting_approval: bool
    approval_state: NotRequired[str]
    approval_decision: NotRequired[str]
    approval_payload: NotRequired[dict]
    current_fix: NotRequired[dict]
    resolved_approvals: NotRequired[list]
    
    # LLM Pause fields
    llm_waiting_state: NotRequired[bool]
    next_retry: NotRequired[str]
    last_llm_model: NotRequired[str]
    last_llm_error: NotRequired[str]
    last_llm_exhaustion_at: NotRequired[str]
    
    confidence_score: float
    security_retry_context: NotRequired[list]
    unresolvable_fixes: NotRequired[list]
    pr_error: NotRequired[str]
    task_id: NotRequired[str]
    touched_symbols: NotRequired[dict]
    dependency_graph: NotRequired[dict]
    rag_status: NotRequired[dict]
