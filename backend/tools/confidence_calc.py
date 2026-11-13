"""Evidence-based pipeline scoring; never a probability of correctness."""


def calculate_pipeline_confidence(state, tests_passed=None, tests_total=None,
                                  security_clean=None, chroma_score=0.0):
    validation = (state.get("validation_results") or [{}])[-1]
    # Syntax/file counts are not passed unit tests. Failed/absent suites earn no test points.
    tests_ratio = 1.0 if validation.get("passed") is True else 0.0
    if validation.get("tests_executed") is False:
        tests_ratio = 0.0
    security_clean = state.get("security_verified", False) if security_clean is None else security_clean
    static_clean = 1.0 if security_clean and validation.get("passed") is True and not state.get("scanners_failed") else 0.0
    latest = {}
    for index, patch in enumerate(state.get("patches", [])):
        latest[str(patch.get("patch_id", index))] = patch
    patches_ratio = sum(p.get("applied") is True for p in latest.values()) / len(latest) if latest else 0.0
    # Only an independently measured retrieval score may supply the RAG component.
    chroma_ratio = max(0.0, min(chroma_score / 100 if chroma_score > 1 else chroma_score, 1.0))
    return round(tests_ratio * 40 + static_clean * 30 + patches_ratio * 20 + chroma_ratio * 10, 1)
