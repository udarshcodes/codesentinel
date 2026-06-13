import hashlib
import json

_cache: dict[str, str] = {}
MAX_CACHE_SIZE = 500

def _make_cache_key(prompt: str, model: str) -> str:
    payload = json.dumps({"prompt": prompt, "model": model}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()

def get_cached(prompt: str, model: str) -> str | None:
    return _cache.get(_make_cache_key(prompt, model))

def set_cached(prompt: str, model: str, response: str) -> None:
    key = _make_cache_key(prompt, model)
    _cache[key] = response
    if len(_cache) > MAX_CACHE_SIZE:
        oldest = next(iter(_cache))
        del _cache[oldest]
