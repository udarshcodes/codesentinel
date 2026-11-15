"""Cumulative worker snapshots and bounded, restart-safe admin aggregation."""
import copy


def merge_usage(baseline, current):
    result = copy.deepcopy(baseline or {})
    for agent, usage in (current or {}).items():
        entry = result.setdefault(agent, {})
        for field in ("calls", "prompt_tokens", "completion_tokens"):
            entry[field] = int(entry.get(field, 0)) + int(usage.get(field, 0))
        entry["model_used"] = sorted(set(entry.get("model_used", [])) | set(usage.get("model_used", [])))
    return result


def capture_usage(state, baseline, cache_baseline):
    from tools.llm_router import get_telemetry
    from tools.response_cache import cache_metrics
    state["llm_telemetry"] = merge_usage(baseline, get_telemetry())
    current = cache_metrics.get("global", {})
    state["worker_cache_metrics"] = {field: int(cache_baseline.get(field, 0)) + int(current.get(field, 0))
                                     for field in ("hits", "misses")}


def aggregate_usage(states):
    agents, cache, reported = {}, {"hits": 0, "misses": 0}, 0
    for state in states:
        try:
            if not isinstance(state, dict) or not state.get("llm_telemetry"):
                continue
            merged = merge_usage(agents, state["llm_telemetry"])
            metrics = state.get("worker_cache_metrics", {})
            updated_cache = {field: cache[field] + int(metrics.get(field, 0)) for field in cache}
            agents, cache = merged, updated_cache
            reported += 1
        except (TypeError, ValueError, AttributeError):
            continue
    return {"agents": agents, "cache": cache, "reported_jobs": reported}
