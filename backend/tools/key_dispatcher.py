import threading
from config import GROQ_API_KEYS, GROQ_EMERGENCY_KEY, GROQ_TOKENS_PER_KEY_PER_DAY
from datetime import date

_lock = threading.Lock()
_state = {
    "index": 0,
    "usage": {i: 0 for i in range(len(GROQ_API_KEYS))},
    "skipped": set(),
    "emergency_active": False,
    "emergency_usage": 0,
    "date": date.today().isoformat(),
}

def _reset_if_new_day():
    today = date.today().isoformat()
    if _state["date"] != today:
        _state["usage"] = {i: 0 for i in range(len(GROQ_API_KEYS))}
        _state["skipped"] = set()
        _state["emergency_active"] = False
        _state["emergency_usage"] = 0
        _state["date"] = today
        print("[KeyDispatcher] New day detected. Usage counters reset.")

def get_next_key() -> tuple[str, int]:
    """
    Return (api_key, key_index) for the next call using round robin.
    key_index of -1 signals the emergency key is being used.
    """
    with _lock:
        _reset_if_new_day()
        available = [i for i in range(len(GROQ_API_KEYS)) if i not in _state["skipped"]]
        
        if not available:
            if GROQ_EMERGENCY_KEY:
                if not _state["emergency_active"]:
                    _state["emergency_active"] = True
                    print("[KeyDispatcher] All primary keys exhausted. Activating emergency key 6.")
                    _fire_alert()
                return GROQ_EMERGENCY_KEY, -1
            raise RuntimeError("[KeyDispatcher] All API keys exhausted including emergency key.")
            
        idx = available[_state["index"] % len(available)]
        _state["index"] += 1
        return GROQ_API_KEYS[idx], idx

def _fire_alert():
    """Non-blocking webhook call. Never raises — alert failure must not break the pipeline."""
    import os, requests
    webhook = os.getenv("ALERT_WEBHOOK_URL", "")
    if not webhook:
        return
    try:
        requests.post(webhook, json={
            "text": "CodeSentinel: all 5 primary Groq keys exhausted. Emergency key 6 is now active."
        }, timeout=3)
    except Exception:
        pass

def record_usage(key_index: int, tokens_used: int):
    """Track tokens consumed. key_index of -1 means emergency key."""
    with _lock:
        if key_index == -1:
            _state["emergency_usage"] += tokens_used
            return
        _state["usage"][key_index] = _state["usage"].get(key_index, 0) + tokens_used
        if _state["usage"][key_index] >= GROQ_TOKENS_PER_KEY_PER_DAY:
            _state["skipped"].add(key_index)
            print(f"[KeyDispatcher] Key index {key_index} hit daily budget. Removing from pool.")

def mark_rate_limited(key_index: int):
    """Called on 429. key_index of -1 means emergency key got rate limited."""
    with _lock:
        if key_index == -1:
            print("[KeyDispatcher] Emergency key also rate limited. No keys remaining.")
            return
        _state["skipped"].add(key_index)
        print(f"[KeyDispatcher] Key index {key_index} rate limited. Rotating out.")

def get_usage_report() -> dict:
    """Returns current token usage across all keys including emergency key."""
    with _lock:
        primary_usage = dict(_state["usage"])
        return {
            "date": _state["date"],
            "primary_keys": {
                str(i): {
                    "tokens_used": primary_usage.get(i, 0),
                    "budget": GROQ_TOKENS_PER_KEY_PER_DAY,
                    "percent_used": round(primary_usage.get(i, 0) / GROQ_TOKENS_PER_KEY_PER_DAY * 100, 1),
                    "status": "exhausted" if i in _state["skipped"] else "active",
                }
                for i in range(len(GROQ_API_KEYS))
            },
            "emergency_key": {
                "available": GROQ_EMERGENCY_KEY is not None,
                "active": _state["emergency_active"],
                "tokens_used": _state["emergency_usage"],
                "budget": GROQ_TOKENS_PER_KEY_PER_DAY,
                "percent_used": round(_state["emergency_usage"] / GROQ_TOKENS_PER_KEY_PER_DAY * 100, 1),
            },
            "summary": {
                "total_tokens_used": sum(primary_usage.values()) + _state["emergency_usage"],
                "total_budget": GROQ_TOKENS_PER_KEY_PER_DAY * (len(GROQ_API_KEYS) + 1),
                "active_primary_keys": len(GROQ_API_KEYS) - len(_state["skipped"]),
                "emergency_engaged": _state["emergency_active"],
            },
        }
