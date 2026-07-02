"""
Unified confidence score calculator for CodeSentinel pipeline.
Used by validator.py and pr_author.py to maintain consistent confidence scores across pipeline steps.
"""


def calculate_pipeline_confidence(
    state: dict,
    tests_passed: int = None,
    tests_total: int = None,
    security_clean: bool = None,
    chroma_score: float = 0.0,
) -> float:
    """
    Calculate confidence score (0.0 to 100.0) based on:
    - 40% automated tests passed
    - 30% clean security scan
    - 20% patches applied successfully
    - 10% historical vector store confidence
    """
    validation_results = state.get("validation_results", [])
    if tests_passed is None or tests_total is None:
        if validation_results:
            latest = validation_results[-1]
            if latest.get("passed"):
                tests_ratio = 1.0
            else:
                fp = latest.get("files_passed", 0)
                ft = latest.get("files_validated", 1)
                tests_ratio = fp / max(ft, 1)
        else:
            tests_ratio = 1.0
    else:
        tests_ratio = tests_passed / max(tests_total, 1) if tests_total > 0 else 1.0

    if security_clean is None:
        security_clean = state.get(
            "security_verified", True if not state.get("static_findings") else False
        )
    static_clean = 1.0 if security_clean else 0.0

    patches = state.get("patches", [])
    if patches:
        applied_count = sum(1 for p in patches if p.get("applied", True))
        patches_ratio = applied_count / len(patches)
    elif state.get("investigated_issues", []):
        patches_ratio = 0.0
    else:
        patches_ratio = 1.0

    chroma_ratio = min(
        chroma_score / 100.0 if chroma_score > 1.0 else chroma_score, 1.0
    )

    score = (
        (tests_ratio * 40.0)
        + (static_clean * 30.0)
        + (patches_ratio * 20.0)
        + (chroma_ratio * 10.0)
    )
    return round(min(score, 100.0), 1)
