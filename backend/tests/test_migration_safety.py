import sqlite3
import pytest
import os
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

@pytest.fixture
def isolated_db():
    # Use a temporary file for the database to test migration safely
    with NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except:
            pass

def setup_legacy_jobs_token(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE jobs (
            task_id TEXT PRIMARY KEY,
            status TEXT,
            approval_token TEXT,
            pipeline_state TEXT,
            approval_expires_at TIMESTAMP,
            worker_attempt_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE approval_credentials (
            credential_id TEXT PRIMARY KEY,
            task_id TEXT,
            fix_id TEXT,
            approval_cycle_id TEXT,
            token_hash TEXT,
            status TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP,
            used_at TIMESTAMP,
            revoked_at TIMESTAMP,
            decision TEXT,
            worker_attempt_id TEXT
        )
    """)
    conn.commit()
    conn.close()

def setup_legacy_approval_cycles(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE jobs (
            task_id TEXT PRIMARY KEY,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE approval_credentials (
            credential_id TEXT PRIMARY KEY,
            task_id TEXT,
            fix_id TEXT,
            approval_cycle_id TEXT,
            token_hash TEXT,
            status TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP,
            used_at TIMESTAMP,
            revoked_at TIMESTAMP,
            decision TEXT,
            worker_attempt_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE approval_cycles (
            approval_cycle_id TEXT,
            task_id TEXT,
            fix_id TEXT,
            token_hash TEXT,
            decision TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP,
            used_at TIMESTAMP,
            worker_attempt_id TEXT
        )
    """)
    conn.commit()
    conn.close()

def test_migration_legacy_job_tokens_fails_closed(isolated_db, monkeypatch):
    from api import job_manager, db
    monkeypatch.setattr(job_manager, 'DB_PATH', isolated_db)
    monkeypatch.setattr(db, 'DB_PATH', isolated_db)
    monkeypatch.setenv("DB_PATH", isolated_db)
    
    setup_legacy_jobs_token(isolated_db)
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    
    # Insert a valid row and a malformed row (invalid JSON)
    cursor.execute("INSERT INTO jobs (task_id, status, approval_token, pipeline_state) VALUES (?, ?, ?, ?)",
                   ("task-1", "WAITING_FOR_APPROVAL", "tok-1", '{"approval_cycle_id": "c1", "approval_payload": {"fix_id": "f1"}}'))
    cursor.execute("INSERT INTO jobs (task_id, status, approval_token, pipeline_state) VALUES (?, ?, ?, ?)",
                   ("task-2", "WAITING_FOR_APPROVAL", "tok-2", 'MALFORMED_JSON_HERE'))
    conn.commit()
    conn.close()
    
    # Should raise an exception and fail initialization
    with pytest.raises(Exception) as excinfo:
        job_manager.init_db()
        
    assert "Migration validation failed for legacy job tokens: Malformed pipeline_state" in str(excinfo.value)
    
    # Verify rollback - legacy table intact, jobs token column still exists
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "approval_token" in columns, "Legacy schema should not be dropped on failed migration"
    
    cursor.execute("SELECT COUNT(*) FROM approval_credentials")
    assert cursor.fetchone()[0] == 0, "No partial records should be committed"
    conn.close()

def test_migration_legacy_approval_cycles_fails_closed(isolated_db, monkeypatch):
    from api import job_manager, db
    monkeypatch.setattr(job_manager, 'DB_PATH', isolated_db)
    monkeypatch.setattr(db, 'DB_PATH', isolated_db)
    monkeypatch.setenv("DB_PATH", isolated_db)
    
    setup_legacy_approval_cycles(isolated_db)
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    
    # Insert a valid row and a malformed row (missing fix_id)
    cursor.execute("INSERT INTO approval_cycles (approval_cycle_id, task_id, fix_id, token_hash) VALUES (?, ?, ?, ?)",
                   ("c1", "task-1", "f1", "hash1"))
    cursor.execute("INSERT INTO approval_cycles (approval_cycle_id, task_id, fix_id, token_hash) VALUES (?, ?, ?, ?)",
                   ("c2", "task-2", None, "hash2")) # missing fix_id
    conn.commit()
    conn.close()
    
    # Should raise exception
    with pytest.raises(Exception) as excinfo:
        job_manager.init_db()
        
    assert "Migration validation failed: Missing required fields" in str(excinfo.value)
    
    # Verify rollback - table still exists
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='approval_cycles'")
    assert cursor.fetchone() is not None, "Legacy table approval_cycles should not be dropped on failed migration"
    conn.close()

def test_migration_legacy_job_v3_fails_closed(isolated_db, monkeypatch):
    from api import job_manager, db
    monkeypatch.setattr(job_manager, 'DB_PATH', isolated_db)
    monkeypatch.setattr(db, 'DB_PATH', isolated_db)
    monkeypatch.setenv("DB_PATH", isolated_db)
    
    # Setup legacy jobs token
    setup_legacy_jobs_token(isolated_db)
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    
    # Insert valid row so that it tries to migrate
    cursor.execute("INSERT INTO jobs (task_id, status, approval_token, pipeline_state) VALUES (?, ?, ?, ?)",
                   ("task-1", "WAITING_FOR_APPROVAL", "tok-1", 'INVALID_JSON_HERE'))
    
    conn.commit()
    conn.close()

    # Should raise exception because of invalid JSON
    with pytest.raises(ValueError, match="Malformed pipeline_state"):
        job_manager.init_db()
        
    # Verify rollback - schema version should not be 3
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
    version = cursor.fetchone()
    # It might be 2 if V1 and V2 succeeded, but not 3
    assert version is None or version[0] < 3
    conn.close()
