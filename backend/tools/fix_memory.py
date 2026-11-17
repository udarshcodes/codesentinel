"""Recover verified repository fix memory from durable job snapshots."""


def verified_fix_records(state):
    latest = (state.get("validation_results") or [{}])[-1]
    if (latest.get("passed") is not True or latest.get("tests_executed") is not True
            or any(latest.get(key) for key in ("build_failed", "suite_failed", "infrastructure_error"))
            or state.get("security_verified") is not True or state.get("scanners_failed")
            or state.get("pipeline_error") or not state.get("pr_url") or state.get("pr_error")):
        return []
    material = set(state.get("material_files") or [])
    issues = {str(issue.get("id")): issue for issue in state.get("investigated_issues", [])}
    # Only the latest attempt for an issue can represent the verified change.
    patches = {str(p.get("patch_id")): p for p in state.get("patches", [])}
    records = []
    for issue_id, patch in patches.items():
        issue = issues.get(issue_id, {})
        description = issue.get("description") or issue.get("original_finding", {}).get("issue")
        text = patch.get("patch_text")
        if (not patch.get("applied") or patch.get("file") not in material
                or not isinstance(description, str) or not description.strip()
                or not isinstance(text, str) or not text.strip() or len(text) > 30000
                or issue.get("remediation_mode") == "manual_review"):
            continue
        records.append({"issue": description[:4000], "patch": text,
                        "confidence": float(state.get("confidence_score") or 0)})
    return records[:20]


def query_repository_memory(repo_url, query):
    from api.job_manager import JobManager
    from tools.vector_store import store_validated_fix, query_similar_fixes

    # PostgreSQL/SQLite job snapshots are authoritative. Rehydrate Chroma after
    # a container replacement instead of trusting its ephemeral filesystem.
    records = []
    for state in JobManager.get_repository_fix_states(repo_url):
        records.extend(verified_fix_records(state))
        if len(records) >= 20:
            break
    for record in records[:20]:
        store_validated_fix(repo_url, record["issue"], record["patch"], record["confidence"], strict=True)
    fixes = query_similar_fixes(repo_url, query, strict=True)
    return {"status": "success", "records_available": min(len(records), 20), "fixes": fixes}


async def retrieve_worker_memory(repo_url, query, *, task_id=None):
    from tools import auth
    from tools.vector_store import query_similar_fixes

    if not task_id:
        return {"status": "local", "fixes": query_similar_fixes(repo_url, query)}
    if task_id != auth.TASK_ID:
        raise ValueError("Fix memory task does not match the worker identity")
    response = await auth.authenticated_post(
        f"/api/v1/job/{auth.TASK_ID}/fix-memory/query", {"query": query[:4000]}, timeout=120.0)
    response.raise_for_status()
    return response.json()
