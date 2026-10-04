import os
import time
import subprocess
import threading
import pytest
from tests.test_migration_safety import setup_legacy_jobs_token
from tools.sandbox_runner import is_docker_available

@pytest.fixture(scope="module")
def postgres_db(request):
    is_explicit = any("test_postgres_integration.py" in arg for arg in request.config.args)
    if not is_docker_available():
        if is_explicit:
            pytest.fail("Docker is required for postgres integration tests, but it is not available.")
        pytest.skip("Docker is required for postgres integration tests")
        
    import socket
    import uuid
    def get_free_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()
        return port
        
    port = get_free_port()
    container_name = f"codesentinel_test_pg_{uuid.uuid4().hex[:8]}"
    
    # Start Postgres
    subprocess.run([
        "docker", "run", "-d",
        "--name", container_name,
        "-e", "POSTGRES_USER=testuser",
        "-e", "POSTGRES_PASSWORD=testpass",
        "-e", "POSTGRES_DB=testdb",
        "-p", f"{port}:5432",
        "postgres:15-alpine"
    ], check=True)
    
    # Wait for DB to be ready
    db_url = f"postgresql://testuser:testpass@localhost:{port}/testdb"
    
    max_retries = 20
    import psycopg2
    for _ in range(max_retries):
        try:
            conn = psycopg2.connect(db_url)
            conn.close()
            break
        except Exception:
            time.sleep(1)
    else:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        pytest.fail("Postgres did not start in time")
        
    orig_db_url = os.environ.get("DATABASE_URL")
    orig_env = os.environ.get("ENVIRONMENT")
    
    os.environ["DATABASE_URL"] = db_url
    os.environ["ENVIRONMENT"] = "production"
    
    try:
        yield db_url
    finally:
        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
            
        if orig_env is not None:
            os.environ["ENVIRONMENT"] = orig_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]
            
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

def test_pg_migrations_and_init(postgres_db):
    """Test that init_db works on a fresh Postgres database."""
    from api.job_manager import init_db
    from api.db import get_connection
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT version()")
    version = c.fetchone()[0]
    assert "PostgreSQL" in version, f"Expected PostgreSQL, got {version}"
    c.execute("SELECT current_database()")
    db_name = c.fetchone()[0]
    assert db_name == "testdb", f"Expected testdb, got {db_name}"
    assert conn.is_postgres is True, "Connection object does not acknowledge Postgres mode"
    conn.close()
    
    # Should not raise any errors
    init_db()
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM llm_global_state")
    assert c.fetchone()[0] == 1
    conn.close()

def test_pg_atomic_job_claim(postgres_db):
    """Test concurrent claiming of jobs to ensure FOR UPDATE locks work correctly."""
    from api.job_manager import JobManager, init_db
    from api.db import get_connection
    import uuid
    
    # Ensure fresh state
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM job_events")
    c.execute("DELETE FROM jobs")
    
    task_id = str(uuid.uuid4())
    now_ts = time.time()
    c.execute(
        "INSERT INTO jobs (task_id, repo_url, status, dispatch_count) VALUES (?, ?, ?, ?)",
        (task_id, "https://github.com/test/repo", "WAITING_FOR_DISPATCH", 0)
    )
    conn.commit()
    conn.close()
    
    # We will launch 5 threads to claim the same job. Only ONE should succeed.
    results = []
    def claim_worker(tid):
        worker_attempt_id = JobManager.claim_waiting_job(task_id)
        results.append(worker_attempt_id)
        
    threads = [threading.Thread(target=claim_worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    # Count how many successful claims
    successful_claims = [r for r in results if r is not None]
    assert len(successful_claims) == 1, f"Expected exactly 1 claim, got {len(successful_claims)}"
    
    # Check that dispatch_count is 1
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT dispatch_count, status FROM jobs WHERE task_id = ?", (task_id,))
    row = c.fetchone()
    conn.close()
    
    assert row[0] == 1, "Dispatch count should be exactly 1"
    assert row[1] == "DISPATCHING", "Status should be DISPATCHING"


def test_pg_job_lifecycle(postgres_db):
    """Test job creation, retrieval, state persistence."""
    from api.job_manager import JobManager
    import uuid
    import time
    
    task_id = str(uuid.uuid4())
    JobManager.create_job(task_id, "https://github.com/test/repo", None)
    
    job = JobManager.get_job(task_id)
    assert job is not None
    assert job["repo_url"] == "https://github.com/test/repo"
    
    attempt_id = JobManager.claim_waiting_job(task_id)
    JobManager.save_worker_state(task_id, attempt_id, "RUNNING", {"file": "content"})
    
    # Stale worker recovery
    # Make it stale
    from api.db import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE jobs SET worker_heartbeat_at = ? WHERE task_id = ?", ((__import__('datetime').datetime.now(__import__('datetime').timezone.utc) - __import__('datetime').timedelta(hours=1)).isoformat(), task_id))
    conn.commit()
    conn.close()
    
    new_attempt = JobManager.recover_stale_worker_claim(task_id)
    assert new_attempt is not None
    assert new_attempt != attempt_id

def test_pg_concurrent_recovery(postgres_db):
    """Test two workers attempting to recover the same stale job."""
    from api.job_manager import JobManager
    from api.db import get_connection
    import uuid
    import time
    import threading
    
    task_id = str(uuid.uuid4())
    JobManager.create_job(task_id, "https://github.com/test/repo", None)
    JobManager.claim_waiting_job(task_id)
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE jobs SET worker_heartbeat_at = ? WHERE task_id = ?", ((__import__('datetime').datetime.now(__import__('datetime').timezone.utc) - __import__('datetime').timedelta(hours=1)).isoformat(), task_id))
    conn.commit()
    conn.close()
    
    results = []
    def recover_worker():
        res = JobManager.recover_stale_worker_claim(task_id)
        results.append(res)
        
    threads = [threading.Thread(target=recover_worker) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    successful = [r for r in results if r is not None]
    assert len(successful) == 1

def test_pg_concurrent_event_creation(postgres_db):
    from api.job_manager import JobManager
    import uuid
    import threading
    
    task_id = str(uuid.uuid4())
    JobManager.create_job(task_id, "https://test", None)
    attempt_id = JobManager.claim_waiting_job(task_id)

    def add_event(i):
        JobManager.add_worker_event(task_id, attempt_id, "RUNNING", f"Event {i}", {}, __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
        
    threads = [threading.Thread(target=add_event, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    events = JobManager.get_events(task_id)
    assert len(events) == 11
    seqs = [e["sequence"] for e in events]
    assert len(set(seqs)) == 11 # No duplicates

def test_pg_approval_lifecycle(postgres_db):
    from api.job_manager import JobManager
    from api.db import get_connection
    import uuid
    import json
    import hashlib
    from datetime import datetime, timezone, timedelta
    
    task_id = str(uuid.uuid4())
    JobManager.create_job(task_id, "https://test", None)
    attempt_id = JobManager.claim_waiting_job(task_id)
    JobManager.save_worker_state(task_id, attempt_id, "RUNNING", {})
    
    pipeline_state = {
        "status": "WAITING_FOR_APPROVAL",
        "awaiting_approval": True,
        "approval_state": "pending",
        "repair_plan": [{"fix_id": "fix1", "status": "pending"}],
        "approval_payload": {"fix_id": "fix1"},
        "approval_cycle_id": "cycle1"
    }
    
    JobManager.save_worker_state(task_id, attempt_id, "WAITING_FOR_APPROVAL", pipeline_state)
    
    raw_token = "my_secret_token"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    cred_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, worker_attempt_id) VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s)",
        (cred_id, task_id, "fix1", "cycle1", token_hash, (now + timedelta(minutes=15)).isoformat(), now.isoformat(), attempt_id)
    )
    conn.commit()
    conn.close()
    
    # Concurrent resolution
    import threading
    results = []
    def resolve_cred():
        try:
            JobManager.resolve_approval(task_id, "approved", token_hash, "fix1", "cycle1")
            results.append(True)
        except Exception as e:
            print("Error resolving approval:", e)
            results.append(False)
            
    threads = [threading.Thread(target=resolve_cred) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    successful = [r for r in results if r is True]
    assert len(successful) == 1

def test_pg_llm_key_concurrency(postgres_db):
    from tools.key_dispatcher import get_next_key, record_usage, get_usage_report
    import threading
    import config
    
    # Mock keys
    import tools.key_dispatcher
    tools.key_dispatcher.GROQ_API_KEYS = [f"fake_key_{i}" for i in range(6)]
    tools.key_dispatcher.GROQ_EMERGENCY_KEY = "fake_emergency"
    
    from api.db import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM llm_key_state")
    for i in range(6):
        c.execute("INSERT INTO llm_key_state (key_index, tokens_used_today, daily_exhausted) VALUES (%s, 0, %s)", (i, False))
    conn.commit()
    conn.close()
    
    def use_key():
        try:
            key, idx = get_next_key()
            if key:
                record_usage(idx, 100)
        except Exception as e:
            print("Error in thread:", e)
            
    errors = []
    threads = [threading.Thread(target=use_key) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    status = get_usage_report()
    total_tokens = sum(k["tokens_used"] for k in status.get("primary_keys", {}).values())
    if errors: print("ERRORS:", errors)
    assert total_tokens == 2000
    
    # Direct database verification
    conn2 = get_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT tokens_used_today FROM llm_key_state")
    rows = c2.fetchall()
    db_total = sum(row[0] for row in rows)
    assert db_total == 2000
    assert all(row[0] >= 0 for row in rows)
    conn2.close()
