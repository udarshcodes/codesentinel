"""
Context Cache — In-memory LRU cache for stable pipeline context.

Caches knowledge graphs, file maps, and dependency info per session
so they are not re-sent in every LLM prompt.

NOTE: This is an in-memory, per-process cache suitable for single-worker
deployments.  If this service scales horizontally to multiple workers,
migrate this layer to a centralized Redis store to avoid per-worker
fragmentation.
"""

import hashlib
from typing import Any

# ---------------------------------------------------------------------------
# Session-scoped cache (dict keyed by repo hash)
# ---------------------------------------------------------------------------
_cache: dict[str, dict[str, Any]] = {}


def _repo_hash(repo_url: str) -> str:
    """Derive a deterministic hash key for a repository URL."""
    return hashlib.sha256(repo_url.encode()).hexdigest()[:16]


def store(repo_url: str, key: str, value: Any) -> None:
    """Store a value in the session cache."""
    h = _repo_hash(repo_url)
    if h not in _cache:
        _cache[h] = {}
    _cache[h][key] = value


def get(repo_url: str, key: str, default: Any = None) -> Any:
    """Retrieve a cached value, or return default."""
    h = _repo_hash(repo_url)
    return _cache.get(h, {}).get(key, default)


def invalidate(repo_url: str) -> None:
    """
    Invalidate all cached context for a repository.
    Call this when a git commit occurs mid-session or the session ends.
    """
    h = _repo_hash(repo_url)
    _cache.pop(h, None)


def get_localized_graph(repo_url: str, target_file: str) -> dict:
    """
    Return only the first-degree dependencies of `target_file` from the
    cached knowledge graph, rather than the full graph.

    This drastically reduces the token count injected into prompts.
    """
    kg = get(repo_url, "knowledge_graph", {})
    if not kg:
        return {}

    # Return a minimal subset: language, framework, and only modules
    # relevant to the target file.
    modules = kg.get("modules") or []
    relevant_modules = [
        m for m in modules if m and _is_related(str(m), target_file)
    ]

    # Include API endpoints and DB interactions relevant to this file
    api_endpoints = kg.get("api_endpoints") or []
    relevant_endpoints = [
        ep
        for ep in api_endpoints
        if isinstance(ep, dict) and _is_related(ep.get("handler_file", ""), target_file)
    ][:5]

    db_interactions = kg.get("db_interactions") or []
    relevant_db = [
        db
        for db in db_interactions
        if isinstance(db, dict) and _is_related(str(db), target_file)
    ][:5]

    return {
        "language": kg.get("language", "unknown"),
        "framework": kg.get("framework", "unknown"),
        "relevant_modules": relevant_modules[:5],  # Cap to 5
        "api_endpoints": relevant_endpoints,
        "db_interactions": relevant_db,
    }


def _is_related(module_name: str, target_file: str) -> bool:
    """Simple heuristic: check if module name overlaps with the file path."""
    module_lower = module_name.lower().replace(".", "/")
    file_lower = target_file.lower()
    return module_lower in file_lower or file_lower in module_lower
