import os
import sqlite3
import threading
from datetime import date, datetime, timezone, timedelta
from config import GROQ_API_KEYS, GROQ_EMERGENCY_KEY, GROQ_TOKENS_PER_KEY_PER_DAY

def _get_db():
    from api.db import get_connection
    return get_connection()

def _reset_if_new_day(cursor):
    today = datetime.now(timezone.utc).date().isoformat()
    cursor.execute("SELECT date_str FROM llm_global_state WHERE id = 1")
    row = cursor.fetchone()
    if not row or row[0] != today:
        now_ts = datetime.now(timezone.utc).isoformat()
        cursor.execute("UPDATE llm_global_state SET date_str = ?, emergency_active = ?, emergency_usage = 0, updated_at = ? WHERE id = 1", (today, False, now_ts))
        cursor.execute("UPDATE llm_key_state SET tokens_used_today = 0, daily_exhausted = ?, updated_at = ?", (False, now_ts,))
        print("[KeyDispatcher] New day detected. Usage counters reset.")

def get_next_key() -> tuple[str, int]:
    """
    Return (api_key, key_index) for the next call using round robin.
    key_index of -1 signals the emergency key is being used.
    """
    conn = _get_db()
    try:
        conn.transaction()
        cursor = conn.cursor()
        
        _reset_if_new_day(cursor)
        
        now_ts = datetime.now(timezone.utc).isoformat()
        
        cursor.execute(conn.for_update("SELECT key_index FROM llm_key_state WHERE daily_exhausted = ? AND (rate_limited_until IS NULL OR rate_limited_until <= ?) ORDER BY key_index"), (False, now_ts,))
        available_rows = cursor.fetchall()
        available = [row[0] for row in available_rows]
        
        if not available:
            if GROQ_EMERGENCY_KEY:
                cursor.execute(conn.for_update("SELECT emergency_active, emergency_rate_limited_until FROM llm_global_state WHERE id = 1"))
                row = cursor.fetchone()
                emergency_active = bool(row[0]) if row else False
                emergency_rate_limited_until = row[1] if row else None
                
                if emergency_rate_limited_until and emergency_rate_limited_until > now_ts:
                    raise RuntimeError("[KeyDispatcher] All API keys and emergency key are exhausted/rate-limited.")
                    
                if not emergency_active:
                    cursor.execute("UPDATE llm_global_state SET emergency_active = ?, updated_at = ? WHERE id = 1", (True, now_ts,))
                    print("[KeyDispatcher] All primary keys exhausted. Activating emergency key 6.")
                    _fire_alert()
                conn.commit()
                return GROQ_EMERGENCY_KEY, -1
            raise RuntimeError("[KeyDispatcher] All API keys exhausted including emergency key.")
            
        cursor.execute(conn.for_update("SELECT current_index FROM llm_global_state WHERE id = 1"))
        row = cursor.fetchone()
        current_index = row[0] if row else 0
        
        idx = available[current_index % len(available)]
        
        cursor.execute("UPDATE llm_global_state SET current_index = ?, updated_at = ? WHERE id = 1", (current_index + 1, now_ts))
        conn.commit()
        return GROQ_API_KEYS[idx], idx
    finally:
        conn.close()

def _fire_alert():
    """Non-blocking webhook call. Never raises — alert failure must not break the pipeline."""

    def _send():
        import httpx
        webhook = os.getenv("ALERT_WEBHOOK_URL", "")
        if not webhook:
            return
        try:
            httpx.post(
                webhook,
                json={"text": "CodeSentinel: all 5 primary Groq keys exhausted. Emergency key 6 is now active."},
                timeout=3,
            )
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

def record_usage(key_index: int, tokens_used: int):
    """Track tokens consumed. key_index of -1 means emergency key."""
    conn = _get_db()
    try:
        conn.transaction()
        cursor = conn.cursor()
        now_ts = datetime.now(timezone.utc).isoformat()
        if key_index == -1:
            cursor.execute("UPDATE llm_global_state SET emergency_usage = emergency_usage + ?, updated_at = ? WHERE id = 1", (tokens_used, now_ts))
        else:
            cursor.execute("UPDATE llm_key_state SET tokens_used_today = tokens_used_today + ?, updated_at = ? WHERE key_index = ?", (tokens_used, now_ts, key_index))
            cursor.execute(conn.for_update("SELECT tokens_used_today FROM llm_key_state WHERE key_index = ?"), (key_index,))
            row = cursor.fetchone()
            if row and row[0] >= GROQ_TOKENS_PER_KEY_PER_DAY:
                cursor.execute("UPDATE llm_key_state SET daily_exhausted = ?, updated_at = ? WHERE key_index = ?", (True, now_ts, key_index))
                print(f"[KeyDispatcher] Key index {key_index} hit daily budget. Removing from pool.")
        conn.commit()
    finally:
        conn.close()

def mark_rate_limited(key_index: int, reset_time: int = 60):
    """Called on 429. key_index of -1 means emergency key got rate limited."""
    conn = _get_db()
    try:
        conn.transaction()
        cursor = conn.cursor()
        now_ts = datetime.now(timezone.utc)
        rate_limited_until = (now_ts + timedelta(seconds=reset_time)).isoformat()
        
        if key_index == -1:
            cursor.execute("UPDATE llm_global_state SET emergency_rate_limited_until = ?, updated_at = ? WHERE id = 1", (rate_limited_until, now_ts.isoformat()))
            print("[KeyDispatcher] Emergency key rate limited. Cooldown persisted.")
        else:
            cursor.execute("UPDATE llm_key_state SET rate_limited_until = ?, updated_at = ? WHERE key_index = ?", (rate_limited_until, now_ts.isoformat(), key_index))
            print(f"[KeyDispatcher] Key index {key_index} rate limited. Rotating out.")
        conn.commit()
    finally:
        conn.close()

def get_usage_report() -> dict:
    """Returns current token usage across all keys including emergency key."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        now_ts = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("SELECT date_str, emergency_active, emergency_usage, emergency_rate_limited_until FROM llm_global_state WHERE id = 1")
        global_row = cursor.fetchone()
        date_str = global_row[0] if global_row else datetime.now(timezone.utc).date().isoformat()
        emergency_active = bool(global_row[1]) if global_row else False
        emergency_usage = global_row[2] if global_row else 0
        emergency_rate_limited_until = global_row[3] if global_row else None
        
        emergency_rate_limited = False
        if emergency_rate_limited_until and emergency_rate_limited_until > now_ts:
            emergency_active = False
            emergency_rate_limited = True
        
        cursor.execute("SELECT key_index, tokens_used_today, rate_limited_until, daily_exhausted FROM llm_key_state")
        rows = cursor.fetchall()
        
        primary_keys_report = {}
        total_tokens_used = 0
        active_primary_keys = 0
        
        for key_index, tokens_used, rate_limited_until, daily_exhausted in rows:
            if key_index >= len(GROQ_API_KEYS):
                continue
                
            status = "active"
            if daily_exhausted:
                status = "exhausted"
            elif rate_limited_until and rate_limited_until > now_ts:
                status = "rate_limited"
                
            if status == "active":
                active_primary_keys += 1
                
            total_tokens_used += tokens_used
            
            primary_keys_report[str(key_index)] = {
                "tokens_used": tokens_used,
                "budget": GROQ_TOKENS_PER_KEY_PER_DAY,
                "percent_used": round(tokens_used / GROQ_TOKENS_PER_KEY_PER_DAY * 100, 1) if GROQ_TOKENS_PER_KEY_PER_DAY else 0,
                "status": status,
            }
            
        return {
            "date": date_str,
            "primary_keys": primary_keys_report,
            "emergency_key": {
                "available": GROQ_EMERGENCY_KEY is not None and not emergency_rate_limited,
                "active": emergency_active,
                "rate_limited": emergency_rate_limited,
                "rate_limited_until": emergency_rate_limited_until,
                "tokens_used": emergency_usage,
                "budget": GROQ_TOKENS_PER_KEY_PER_DAY,
                "percent_used": round(emergency_usage / GROQ_TOKENS_PER_KEY_PER_DAY * 100, 1) if GROQ_TOKENS_PER_KEY_PER_DAY else 0,
            },
            "overview": {
                "total_tokens_used": total_tokens_used + emergency_usage,
                "total_budget": GROQ_TOKENS_PER_KEY_PER_DAY * (len(GROQ_API_KEYS) + 1),
                "active_primary_keys": active_primary_keys,
                "emergency_engaged": emergency_active,
            },
        }
    finally:
        conn.close()
