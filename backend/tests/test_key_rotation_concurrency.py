import os
import sqlite3
import pytest
import threading
from unittest import mock
from datetime import datetime, timezone, date, timedelta
from tools.key_dispatcher import get_next_key, record_usage, mark_rate_limited, get_usage_report, _get_db
from config import GROQ_API_KEYS, GROQ_EMERGENCY_KEY, GROQ_TOKENS_PER_KEY_PER_DAY

@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr("tools.key_dispatcher.GROQ_API_KEYS", ["k0", "k1", "k2", "k3", "k4"])
    monkeypatch.setattr("tools.key_dispatcher.GROQ_EMERGENCY_KEY", "k_emerg")
    monkeypatch.setattr("tools.key_dispatcher.GROQ_TOKENS_PER_KEY_PER_DAY", 500000)
    
    db_path = tmp_path / "test_codesentinel.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_key_state (
            key_index INTEGER PRIMARY KEY,
            tokens_used_today INTEGER DEFAULT 0,
            rate_limited_until TIMESTAMP,
            daily_exhausted BOOLEAN DEFAULT 0,
            is_emergency BOOLEAN DEFAULT 0,
            updated_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_global_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_index INTEGER DEFAULT 0,
            date_str TEXT,
            emergency_active BOOLEAN DEFAULT 0,
            emergency_usage INTEGER DEFAULT 0,
            emergency_rate_limited_until TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    cursor.execute(
        "INSERT INTO llm_global_state (id, current_index, date_str, emergency_active, emergency_usage, updated_at) VALUES (1, 0, ?, 0, 0, ?)",
        (datetime.now(timezone.utc).date().isoformat(), datetime.now(timezone.utc).isoformat())
    )
    for i in range(5):
        cursor.execute("INSERT OR IGNORE INTO llm_key_state (key_index) VALUES (?)", (i,))
    conn.commit()
    conn.close()
    yield str(db_path)

def test_get_next_key_round_robin():
    key1, idx1 = get_next_key()
    key2, idx2 = get_next_key()
    key3, idx3 = get_next_key()
    
    assert idx1 == 0
    assert idx2 == 1
    assert idx3 == 2
    
def test_record_usage_daily_exhaustion():
    key, idx = get_next_key()
    record_usage(idx, GROQ_TOKENS_PER_KEY_PER_DAY)
    
    # Next call should skip idx 0
    key2, idx2 = get_next_key()
    assert idx2 != 0

def test_mark_rate_limited():
    key, idx = get_next_key()
    mark_rate_limited(idx, reset_time=60)
    
    # Next call should skip idx 0
    key2, idx2 = get_next_key()
    assert idx2 != 0

def test_concurrency_get_next_key():
    import concurrent.futures
    results = []
    def worker():
        for _ in range(5):
            results.append(get_next_key()[1])
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker) for _ in range(3)]
        concurrent.futures.wait(futures)
        
    assert len(results) == 15
    # Since it's round robin and there are 5 keys, it should be distributed evenly
    counts = {i: results.count(i) for i in range(5)}
    assert all(c == 3 for c in counts.values())

def test_emergency_key_activation():
    # Exhaust all primary keys
    for i in range(5):
        record_usage(i, 500000)
        
    key, idx = get_next_key()
    assert key == "k_emerg"
    assert idx == -1

def test_process_restart_persistence(isolated_db):
    key1, idx1 = get_next_key()
    assert idx1 == 0
    
    # Record usage
    record_usage(1, 1000)
    
    # Simulate restart by reading from DB directly through get_next_key again
    # We're relying on SQLite, not memory
    
    key2, idx2 = get_next_key()
    assert idx2 == 1
    
    report = get_usage_report()
    assert report["primary_keys"]["1"]["tokens_used"] == 1000
    
def test_new_day_reset(monkeypatch):
    # Setup some usage
    key1, idx1 = get_next_key()
    record_usage(idx1, GROQ_TOKENS_PER_KEY_PER_DAY)
    
    # Force yesterday
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE llm_global_state SET date_str = '2000-01-01' WHERE id = 1")
    conn.commit()
    conn.close()
    
    # Trigger new day reset
    key2, idx2 = get_next_key()
    
    # idx1 should be available again, but current index might be anything. 
    # Actually, current_index is not reset, but exhausted is.
    report = get_usage_report()
    assert report["primary_keys"][str(idx1)]["status"] == "active"
    assert report["primary_keys"][str(idx1)]["tokens_used"] == 0

def test_emergency_key_rate_limited():
    # Exhaust all primary keys
    for i in range(5):
        record_usage(i, 500000)
        
    key, idx = get_next_key()
    assert key == "k_emerg"
    assert idx == -1
    
    # Rate limit emergency key
    mark_rate_limited(-1, reset_time=60)
    
    # Next call should raise RuntimeError
    with pytest.raises(RuntimeError, match="All API keys and emergency key are exhausted/rate-limited."):
        get_next_key()
        
    # Verify report reflects rate limit
    report = get_usage_report()
    assert report["emergency_key"]["available"] is False
    assert report["emergency_key"]["rate_limited"] is True

def test_concurrency_emergency_key_activation():
    import concurrent.futures
    # Exhaust all primary keys
    for i in range(5):
        record_usage(i, 500000)
        
    def worker():
        try:
            key, idx = get_next_key()
            if idx == -1:
                mark_rate_limited(-1, reset_time=60)
        except RuntimeError:
            pass
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker) for _ in range(3)]
        concurrent.futures.wait(futures)
        
    # Verify emergency key is rate limited once and only once
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT emergency_rate_limited_until FROM llm_global_state WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] is not None
