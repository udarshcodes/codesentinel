import sqlite3
import json
import os
from datetime import datetime, timezone
import asyncio
from typing import Optional, List, Dict
import secrets
from api.db import get_connection, DB_PATH

def init_db():
    conn = get_connection()
    is_pg = conn.is_postgres
    cursor = conn.cursor()
    
    # 1. Ensure migrations table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP
        )
    """)
    
    cursor.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
    row = cursor.fetchone()
    current_version = row[0] if row else 0
    
    if current_version < 1:
        if not is_pg:
            conn.transaction()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    task_id TEXT PRIMARY KEY,
                    repo_url TEXT,
                    status TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    pipeline_state TEXT,
                    approval_decision TEXT,
                    dispatch_attempted_at TIMESTAMP,
                    dispatch_count INTEGER DEFAULT 0,
                    last_dispatch_error TEXT,
                    worker_attempt_id TEXT,
                    commit_sha TEXT,
                    view_token TEXT,
                    worker_started_at TIMESTAMP,
                    worker_heartbeat_at TIMESTAMP,
                    next_retry TIMESTAMP
                )
            """)
            auto_inc = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS job_events (
                    id {auto_inc},
                    task_id TEXT,
                    sequence INTEGER,
                    status TEXT,
                    event_name TEXT,
                    data TEXT,
                    timestamp TIMESTAMP,
                    UNIQUE(task_id, sequence)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sse_capabilities (
                    token TEXT PRIMARY KEY,
                    task_id TEXT,
                    expires_at TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS approval_credentials (
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
                CREATE UNIQUE INDEX IF NOT EXISTS idx_active_credential 
                ON approval_credentials(approval_cycle_id) 
                WHERE status = 'active'
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_credential_per_task 
                ON approval_credentials(task_id) 
                WHERE status = 'active'
            """)
            cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (1, CURRENT_TIMESTAMP)")
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Migration V1 failed: {e}")

    if current_version < 2:
        if not is_pg:
            conn.transaction()
        try:
            # Migrate data from legacy approval_cycles safely
            if is_pg:
                cursor.execute("SELECT tablename FROM pg_tables WHERE tablename='approval_cycles'")
            else:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='approval_cycles'")
            
            if cursor.fetchone():
                cursor.execute("SELECT approval_cycle_id, task_id, fix_id, token_hash, decision, expires_at, created_at, used_at, worker_attempt_id FROM approval_cycles")
                legacy_cycles = cursor.fetchall()
                
                migrated_count = 0
                expected_count = len(legacy_cycles)
                
                for cycle_id, task_id, fix_id, token_hash, decision, expires_at, created_at, used_at, worker_attempt in legacy_cycles:
                    if not cycle_id or not task_id or not fix_id or not token_hash:
                        raise ValueError(f"Migration validation failed: Missing required fields on legacy approval_cycle record. (task_id: {task_id}, cycle_id: {cycle_id})")
                        
                    cursor.execute("""
                        INSERT INTO approval_credentials 
                        (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, used_at, revoked_at, decision, worker_attempt_id)
                        VALUES (
                            ?, ?, ?, ?, ?, 
                            CASE 
                                WHEN ? IS NOT NULL THEN 'used'
                                WHEN ? < CURRENT_TIMESTAMP THEN 'expired'
                                ELSE 'active'
                            END, 
                            ?, ?, ?, NULL, ?, ?
                        )
                    """, (
                        cycle_id, task_id, fix_id, cycle_id, token_hash,
                        decision, expires_at,
                        expires_at, created_at, used_at, decision, worker_attempt
                    ))
                    migrated_count += 1
                    
                if migrated_count != expected_count:
                    raise ValueError(f"Migration validation failed for approval_cycles. Expected {expected_count} successful migrations but got {migrated_count}.")
                    
                cursor.execute("DROP TABLE approval_cycles")
            
            cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (2, CURRENT_TIMESTAMP)")
            conn.commit()
        except Exception as e:
            print(f"CRITICAL: approval_cycles legacy migration V2 failed. Rolling back database. Error: {e}")
            conn.rollback()
            raise

    if current_version < 3:
        if not is_pg:
            conn.transaction()
        try:
            if is_pg:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='jobs' AND column_name='approval_token'")
                has_legacy = bool(cursor.fetchone())
            else:
                try:
                    cursor.execute("SELECT approval_token, approval_expires_at FROM jobs LIMIT 1")
                    has_legacy = True
                except Exception:
                    has_legacy = False

            if has_legacy:
                import uuid
                import hashlib
                
                cursor.execute("SELECT task_id, approval_token, pipeline_state, approval_expires_at, worker_attempt_id, status FROM jobs WHERE approval_token IS NOT NULL")
                legacy_jobs = cursor.fetchall()
                
                migrated_count = 0
                expected_count = len(legacy_jobs)
                
                for t_id, token, p_state_str, expires, worker_attempt, status in legacy_jobs:
                    if not p_state_str:
                        raise ValueError(f"Migration validation failed for legacy job tokens: Missing pipeline_state on task {t_id}")
                        
                    try:
                        p_state = json.loads(p_state_str)
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Migration validation failed for legacy job tokens: Malformed pipeline_state on task {t_id}. Error: {e}")
                        
                    cycle_id = p_state.get("approval_cycle_id")
                    fix_payload = p_state.get("approval_payload", {})
                    fix_id = fix_payload.get("fix_id")
                    
                    if not cycle_id or not fix_id:
                        raise ValueError(f"Migration validation failed for legacy job tokens: Missing fix_id or cycle_id in pipeline_state on task {t_id}")
                        
                    token_hash = hashlib.sha256(token.encode()).hexdigest()
                    cred_id = str(uuid.uuid4())
                    
                    cred_status = 'active' if status == 'WAITING_FOR_APPROVAL' else 'used'
                    
                    cursor.execute("""
                        INSERT INTO approval_credentials 
                        (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, worker_attempt_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                    """, (cred_id, t_id, fix_id, cycle_id, token_hash, cred_status, expires, worker_attempt))
                    migrated_count += 1
                        
                if migrated_count != expected_count:
                    raise ValueError(f"Migration validation failed. Expected {expected_count} successful migrations but got {migrated_count}.")
                    
                for col in ["approval_token", "approval_used", "approval_expires_at"]:
                    if is_pg:
                        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='jobs'")
                    else:
                        cursor.execute("PRAGMA table_info(jobs)")
                        
                    columns = [row[0] if is_pg else row[1] for row in cursor.fetchall()]
                    if col in columns:
                        cursor.execute(f"ALTER TABLE jobs DROP COLUMN {col}")
                        
            cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (3, CURRENT_TIMESTAMP)")
            conn.commit()
        except Exception as e:
            print(f"CRITICAL: Legacy jobs token schema migration V3 failed. Rolling back database. Error: {e}")
            conn.rollback()
            raise

    if current_version < 4:
        if not is_pg:
            conn.transaction()
        try:
            bool_type = "BOOLEAN" if is_pg else "BOOLEAN DEFAULT 0"
            if is_pg:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS llm_key_state (
                        key_index INTEGER PRIMARY KEY,
                        tokens_used_today INTEGER DEFAULT 0,
                        rate_limited_until TIMESTAMP,
                        daily_exhausted BOOLEAN DEFAULT FALSE,
                        is_emergency BOOLEAN DEFAULT FALSE,
                        updated_at TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS llm_global_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        current_index INTEGER DEFAULT 0,
                        date_str TEXT,
                        emergency_active BOOLEAN DEFAULT FALSE,
                        emergency_usage INTEGER DEFAULT 0,
                        updated_at TIMESTAMP
                    )
                """)
            else:
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
                        updated_at TIMESTAMP
                    )
                """)
            
            cursor.execute("SELECT COUNT(*) FROM llm_global_state")
            if cursor.fetchone()[0] == 0:
                from datetime import date, datetime, timezone
                cursor.execute(
                    "INSERT INTO llm_global_state (id, current_index, date_str, emergency_active, emergency_usage, updated_at) VALUES (1, 0, ?, FALSE, 0, ?)" if is_pg else "INSERT INTO llm_global_state (id, current_index, date_str, emergency_active, emergency_usage, updated_at) VALUES (1, 0, ?, 0, 0, ?)",
                    (datetime.now(timezone.utc).date().isoformat(), datetime.now(timezone.utc).isoformat())
                )
            
            from config import GROQ_API_KEYS
            for i in range(len(GROQ_API_KEYS)):
                if is_pg:
                    cursor.execute("INSERT INTO llm_key_state (key_index) VALUES (?) ON CONFLICT DO NOTHING", (i,))
                else:
                    cursor.execute("INSERT OR IGNORE INTO llm_key_state (key_index) VALUES (?)", (i,))
                
            cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (4, CURRENT_TIMESTAMP)")
            conn.commit()
        except Exception as e:
            print(f"CRITICAL: Key state schema migration V4 failed. Rolling back database. Error: {e}")
            conn.rollback()
            raise

    if current_version < 5:
        if not is_pg:
            conn.transaction()
        try:
            cursor.execute("ALTER TABLE llm_global_state ADD COLUMN emergency_rate_limited_until TIMESTAMP")
            cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (5, CURRENT_TIMESTAMP)")
            conn.commit()
        except Exception as e:
            # If column already exists due to an interrupted migration, that's fine
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                if is_pg:
                    cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (5, CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING")
                else:
                    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (5, CURRENT_TIMESTAMP)")
                conn.commit()
            else:
                print(f"CRITICAL: Key state schema migration V5 failed. Rolling back database. Error: {e}")
                conn.rollback()
                raise

    conn.close()

init_db()


class JobManager:
    @staticmethod
    def validate_approval_context(cursor, task_id: str, request_cycle_id: str, request_fix_id: str, request_worker_id: str = None, require_active_credential: bool = True) -> tuple:
        """
        Authoritative validator for any approval action (issue, recover, resolve).
        Must be executed within a BEGIN EXCLUSIVE transaction using the provided cursor.
        Returns (current_worker_attempt_id, active_credential_row) or raises ValueError.
        """
        cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT status, pipeline_state, worker_attempt_id FROM jobs WHERE task_id = ?"), (task_id,))
        job_row = cursor.fetchone()
        
        if not job_row:
            raise ValueError("Job not found")
            
        current_status, p_state_str, current_worker_id = job_row
        
        if current_status != "WAITING_FOR_APPROVAL":
            raise ValueError("Task is not in a state that can be approved")
            
        if request_worker_id and current_worker_id and current_worker_id != request_worker_id:
            raise ValueError("Stale worker attempt detected")
            
        if not p_state_str:
            raise ValueError("Pipeline state missing")

        try:
            p_state = json.loads(p_state_str)
        except json.JSONDecodeError:
            raise ValueError("Malformed pipeline state")
                
        if not p_state.get("awaiting_approval"):
            raise ValueError("Pipeline is not awaiting approval")
            
        if p_state.get("approval_state") != "pending":
            raise ValueError("Approval state is not pending")
            
        cycle_id = p_state.get("approval_cycle_id")
        fix = p_state.get("approval_payload")
        
        if not cycle_id:
            raise ValueError("Missing approval_cycle_id in pipeline state")
        if not fix:
            raise ValueError("Missing approval_payload in pipeline state")
            
        fix_id = fix.get("fix_id")
        if not fix_id:
            raise ValueError("Missing fix_id in approval_payload")
            
        repair_plan = p_state.get("repair_plan", [])
        plan_fix = next((f for f in repair_plan if f.get("fix_id") == fix_id), None)
        if not plan_fix:
            raise ValueError(f"Fix {fix_id} not found in repair plan")
        if plan_fix.get("status") != "pending":
            raise ValueError(f"Fix {fix_id} is not pending")
            
        if request_cycle_id and request_cycle_id != cycle_id:
            raise ValueError("Approval cycle mismatch. Cannot operate on a stale cycle.")
            
        if request_fix_id and request_fix_id != fix_id:
            raise ValueError("fix_id mismatch")
            
        cursor.execute(
            "SELECT credential_id, worker_attempt_id, token_hash, expires_at FROM approval_credentials WHERE approval_cycle_id = ? AND status = 'active' AND task_id = ? AND fix_id = ?",
            (cycle_id, task_id, fix_id)
        )
        active_cred_row = cursor.fetchone()
        
        if active_cred_row:
            credential_id, cred_worker_attempt_id, token_hash, expires_at_str = active_cred_row
            from datetime import datetime, timezone
            expires_at = expires_at_str if not isinstance(expires_at_str, str) else datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            
            if expires_at <= now:
                # Atomically transition expired credential
                cursor.execute(
                    "UPDATE approval_credentials SET status = 'expired' WHERE credential_id = ?",
                    (credential_id,)
                )
                active_cred_row = None
        
        if require_active_credential and not active_cred_row:
            raise ValueError("Active approval credential not found or belongs to a different task")
            
        return p_state_str, current_worker_id, active_cred_row
    STARTING = "STARTING"
    CLONING_REPOSITORY = "CLONING_REPOSITORY"
    INSTALLING_DEPENDENCIES = "INSTALLING_DEPENDENCIES"
    RUNNING_SCANNERS = "RUNNING_SCANNERS"
    COLLECTING_RESULTS = "COLLECTING_RESULTS"
    AI_ANALYSIS = "AI_ANALYSIS"
    GENERATING_PATCH = "GENERATING_PATCH"
    VALIDATING_PATCH = "VALIDATING_PATCH"
    CREATING_PULL_REQUEST = "CREATING_PULL_REQUEST"
    UPLOADING_RESULTS = "UPLOADING_RESULTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_FOR_DISPATCH = "WAITING_FOR_DISPATCH"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    WAITING_FOR_LLM_CAPACITY = "WAITING_FOR_LLM_CAPACITY"
    RETRYING = "RETRYING"
    NEEDS_REVIEW = "NEEDS_REVIEW"

    TERMINAL_STATES = {"COMPLETED", "FAILED", "NEEDS_REVIEW"}

    VALID_TRANSITIONS = {
        "QUEUED": {"STARTING", "WAITING_FOR_DISPATCH"},
        "WAITING_FOR_DISPATCH": {"DISPATCHING", "FAILED", "NEEDS_REVIEW"},
        "DISPATCHING": {"STARTING", "RUNNING", "FAILED", "WAITING_FOR_DISPATCH"},
        "STARTING": {"RUNNING", "FAILED"},
        "RUNNING": {"WAITING_FOR_APPROVAL", "WAITING_FOR_LLM_CAPACITY", "COMPLETED", "FAILED"},
        "WAITING_FOR_LLM_CAPACITY": {"DISPATCHING", "FAILED", "NEEDS_REVIEW"},
        "WAITING_FOR_APPROVAL": {"NEEDS_REVIEW", "WAITING_FOR_DISPATCH", "FAILED"},
        "RETRYING": {"DISPATCHING", "WAITING_FOR_DISPATCH", "FAILED"},
        "COMPLETED": set(),
        "FAILED": set(),
        "NEEDS_REVIEW": set()
    }

    @classmethod
    def check_database_ready(cls) -> bool:
        try:
            conn = get_connection()
            conn.execute("SELECT 1 FROM jobs LIMIT 1")
            conn.close()
            return True
        except Exception:
            return False

    @classmethod
    def _is_valid_transition(cls, current: str, target: str) -> bool:
        if current in cls.TERMINAL_STATES:
            return False
            
        allowed = cls.VALID_TRANSITIONS.get(current, set())
        return target in allowed

    @classmethod
    def _check_llm_cooldown(cls, next_retry: str) -> tuple[bool, bool]:
        """
        Parses next_retry and evaluates cooldown expiration.
        Returns (can_claim, is_malformed).
        - (False, True): Metadata is missing or malformed (fail closed).
        - (False, False): Valid but in the future (cooldown active).
        - (True, False): Valid and in the past (eligible for claim).
        """
        if not next_retry:
            return False, True
            
        try:
            from datetime import datetime, timezone
            retry_ts = (next_retry.timestamp() if not isinstance(next_retry, str) else datetime.fromisoformat(next_retry.replace("Z", "+00:00")).timestamp())
            current_ts = datetime.now(timezone.utc).timestamp()
            if current_ts < retry_ts:
                return False, False
            return True, False
        except ValueError:
            return False, True

    @classmethod
    def transition_job_state(
        cls,
        cursor,
        task_id: str,
        target_status: str,
        worker_attempt_id: Optional[str] = None,
        enforce_worker_fencing: bool = False,
        pipeline_state: Optional[dict] = None,
        event_name: Optional[str] = None,
        event_data: Optional[dict] = None,
        timestamp: Optional[str] = None,
        extra_updates: Optional[dict] = None,
        sequence: Optional[int] = None
    ) -> tuple[bool, Optional[int]]:
        """
        Authoritative state transition logic.
        Assumes `cursor` is inside an active transaction.
        Does NOT commit. The caller must commit.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
            
        cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT status, worker_attempt_id, pipeline_state FROM jobs WHERE task_id = ?"), (task_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Task not found")
            
        current_status, current_attempt, p_state_str = row
        
        if enforce_worker_fencing:
            if not current_attempt or worker_attempt_id != current_attempt:
                raise ValueError("Stale worker attempt")
                
        if not cls._is_valid_transition(current_status, target_status):
            raise ValueError(f"Invalid state transition: {current_status} -> {target_status}")
            
        if pipeline_state is not None:
            p_state_to_validate = pipeline_state
        else:
            p_state_to_validate = json.loads(p_state_str) if p_state_str else {}
            
        if target_status != "WAITING_FOR_LLM_CAPACITY":
            if extra_updates is None:
                extra_updates = {}
            cls.clear_llm_waiting_state(p_state_to_validate, extra_updates)
            
        if target_status in cls.TERMINAL_STATES:
            p_state_to_validate.pop("awaiting_approval", None)
            p_state_to_validate.pop("approval_state", None)
            p_state_to_validate.pop("llm_waiting_state", None)

        cls.validate_state_consistency(cursor, task_id, target_status, p_state_to_validate)
        p_state_val = json.dumps(p_state_to_validate)
            
        update_cols = ["status = ?", "updated_at = ?"]
        update_vals = [target_status, timestamp]
        
        update_cols.append("pipeline_state = ?")
        update_vals.append(p_state_val)
            
        if extra_updates:
            for k, v in extra_updates.items():
                update_cols.append(f"{k} = ?")
                update_vals.append(v)
                
        update_vals.append(task_id)
        if enforce_worker_fencing:
            update_cols_str = ", ".join(update_cols)
            cursor.execute(f"UPDATE jobs SET {update_cols_str} WHERE task_id = ? AND worker_attempt_id = ?", tuple(update_vals + [worker_attempt_id]))
            if cursor.rowcount == 0:
                raise ValueError("Stale worker attempt during update")
        else:
            update_cols_str = ", ".join(update_cols)
            cursor.execute(f"UPDATE jobs SET {update_cols_str} WHERE task_id = ?", tuple(update_vals))
            
        if event_name:
            if sequence is None:
                cursor.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE task_id = ?", (task_id,))
                sequence = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO job_events (task_id, sequence, status, event_name, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, sequence, target_status, event_name, json.dumps(event_data or {}), timestamp)
            )
            
        return True, sequence

    # In-memory pub/sub queues for SSE streaming, avoiding DB polling.
    _live_queues: Dict[str, List[asyncio.Queue]] = {}
    _sse_queues_lock = asyncio.Lock()
    
    # Events that carry specific state-signaling metadata and require schema validation
    STATE_SIGNALING_EVENTS = {
        "approval_required",
        "approval_resolved",
        "waiting_for_llm_capacity",
        "pipeline_started",
        "pipeline_complete",
        "pipeline_error"
    }

    @classmethod
    def create_job(cls, task_id: str, repo_url: str, view_token: str = None, commit_sha: str = None):
        import hashlib
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        hashed_view = None
        if view_token:
            hashed_view = hashlib.sha256(view_token.encode()).hexdigest()
            
        cursor.execute(
            "INSERT INTO jobs (task_id, repo_url, status, created_at, updated_at, pipeline_state, commit_sha, view_token) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, repo_url, "WAITING_FOR_DISPATCH", now, now, None, commit_sha, hashed_view),
        )
        conn.commit()
        conn.close()

    @classmethod
    def add_worker_event(
        cls,
        task_id: str,
        worker_attempt_id: str,
        status: str,
        event_name: str,
        data: dict,
        timestamp: str,
        sequence: Optional[int] = None,
    ) -> tuple[bool, int]:
        if not worker_attempt_id:
            raise ValueError("worker_attempt_id is required for external worker events")
            
        conn = get_connection()
        cursor = conn.cursor()
        try:
            conn.transaction()
            cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT status, worker_attempt_id, pipeline_state FROM jobs WHERE task_id = ?"), (task_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Task not found")
                
            current_status, current_attempt, p_state_str = row
            if worker_attempt_id != current_attempt:
                raise ValueError("Stale worker attempt")
                
            if event_name == "approval_resolved":
                raise ValueError("Worker is not authorized to emit approval_resolved events")
                
            if current_status == "WAITING_FOR_APPROVAL" and status != current_status:
                raise ValueError("Worker is not authorized to transition state while human approval is pending")
                
            if event_name in cls.STATE_SIGNALING_EVENTS:
                cls._validate_event_semantics(current_status, status, event_name, data, p_state_str)
                
            if current_status == status:
                # Informational event, do not run state transition logic
                if sequence is None:
                    cursor.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE task_id = ?", (task_id,))
                    sequence = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO job_events (task_id, sequence, status, event_name, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (task_id, sequence, status, event_name, json.dumps(data or {}), timestamp)
                )
                success = True
            else:
                success, sequence = cls.transition_job_state(
                    cursor=cursor,
                    task_id=task_id,
                    target_status=status,
                    worker_attempt_id=worker_attempt_id,
                    enforce_worker_fencing=True,
                    event_name=event_name,
                    event_data=data,
                    timestamp=timestamp,
                    sequence=sequence
                )
            conn.commit()
        except (sqlite3.IntegrityError, Exception) as e:
            if type(e).__name__ == 'IntegrityError' or (hasattr(e, '__class__') and e.__class__.__name__ == 'UniqueViolation'):
                success = False
            else:
                conn.rollback()
                raise
            conn.rollback()
        finally:
            conn.close()

        if success:
            cls._broadcast_event(task_id, event_name, data, status, sequence, timestamp)
        return success, sequence

    @classmethod
    def record_informational_event(
        cls,
        task_id: str,
        status: str,
        event_name: str,
        data: dict,
        timestamp: str,
        sequence: Optional[int] = None,
    ) -> tuple[bool, int]:
        """
        Records an event without executing state transition logic.
        NOTE: This method is strictly for internal testing and is NOT concurrency-safe 
        for production use, as it bypasses row-level locking (FOR UPDATE). 
        Do not call this from production code; use add_worker_event instead.
        """
        conn = get_connection()
        cursor = conn.cursor()
        success = True
        try:
            conn.transaction()
            if sequence is None:
                cursor.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE task_id = ?", (task_id,))
                sequence = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO job_events (task_id, sequence, status, event_name, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, sequence, status, event_name, json.dumps(data or {}), timestamp)
            )
            conn.commit()
        except (sqlite3.IntegrityError, Exception) as e:
            if type(e).__name__ == 'IntegrityError' or (hasattr(e, '__class__') and e.__class__.__name__ == 'UniqueViolation'):
                success = False
            else:
                conn.rollback()
                raise
            conn.rollback()
        finally:
            conn.close()

        if success:
            cls._broadcast_event(task_id, event_name, data, status, sequence, timestamp)
        return success, sequence

    @classmethod
    def _validate_event_semantics(cls, current_status: str, event_status: str, event_name: str, data: dict, pipeline_state_str: Optional[str]):
        """Validate state-signaling event payloads and constraints before accepting them."""
        p_state = json.loads(pipeline_state_str) if pipeline_state_str else {}
        
        if event_name == "approval_required":
            if current_status != "WAITING_FOR_APPROVAL":
                raise ValueError(f"approval_required requires current status WAITING_FOR_APPROVAL, got {current_status}")
            if event_status != "WAITING_FOR_APPROVAL":
                raise ValueError("approval_required event status must be WAITING_FOR_APPROVAL")
            if not data.get("fix_id") or not data.get("approval_cycle_id"):
                raise ValueError("approval_required missing fix_id or approval_cycle_id")
            if p_state.get("approval_cycle_id") != data["approval_cycle_id"]:
                raise ValueError("approval_cycle_id mismatch")
            payload = p_state.get("approval_payload", {})
            if payload.get("fix_id") != data["fix_id"]:
                raise ValueError("fix_id mismatch")
            if not p_state.get("awaiting_approval") or p_state.get("approval_state") != "pending":
                raise ValueError("Pipeline state does not reflect a pending approval")
                
        elif event_name == "approval_resolved":
            if event_status not in ("WAITING_FOR_DISPATCH", "NEEDS_REVIEW"):
                raise ValueError("approval_resolved event status must be WAITING_FOR_DISPATCH or NEEDS_REVIEW")
            if "decision" not in data or "fix_id" not in data or "approval_cycle_id" not in data:
                raise ValueError("approval_resolved missing decision, fix_id, or approval_cycle_id")
                
        elif event_name == "waiting_for_llm_capacity":
            if current_status != "WAITING_FOR_LLM_CAPACITY":
                raise ValueError("waiting_for_llm_capacity requires current status WAITING_FOR_LLM_CAPACITY")
            if not p_state.get("llm_waiting_state"):
                raise ValueError("Pipeline state missing llm_waiting_state")
            if not data.get("next_retry") or data.get("next_retry") != p_state.get("next_retry"):
                raise ValueError("next_retry mismatch")
                
        elif event_name == "pipeline_started":
            if event_status != "STARTING":
                raise ValueError("pipeline_started requires event status STARTING")
                
        elif event_name == "pipeline_complete":
            if event_status != "COMPLETED":
                raise ValueError("pipeline_complete requires event status COMPLETED")
                
        elif event_name == "pipeline_error":
            if event_status != "FAILED":
                raise ValueError("pipeline_error requires event status FAILED")

    @classmethod
    def _broadcast_event(cls, task_id: str, event_name: str, data: dict, status: str, sequence: int, timestamp: str):
        """Internal helper to deduplicate SSE broadcasting."""
        if task_id in cls._live_queues:
            event_payload = {
                "event": event_name,
                "data": data,
                "status": status,
                "sequence": sequence,
                "timestamp": timestamp,
            }
            for q in cls._live_queues[task_id]:
                try:
                    q.put_nowait(event_payload)
                except asyncio.QueueFull:
                    pass

    @classmethod
    def get_job(cls, task_id: str) -> Optional[dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT task_id, repo_url, status, created_at, updated_at, pipeline_state, 
                      approval_decision, commit_sha, view_token,
                      worker_started_at, worker_heartbeat_at, next_retry, worker_attempt_id
               FROM jobs WHERE task_id = ?""",
            (task_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "task_id": row[0],
            "repo_url": row[1],
            "status": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "pipeline_state": json.loads(row[5]) if row[5] else None,
            "approval_decision": row[6],
            "commit_sha": row[7],
            "view_token": row[8],
            "worker_started_at": row[9],
            "worker_heartbeat_at": row[10],
            "next_retry": row[11],
            "worker_attempt_id": row[12]
        }

    @classmethod
    def to_public_dict(cls, job: dict) -> dict:
        if not job:
            return None
        safe = dict(job)
        safe.pop("view_token", None)
        safe.pop("worker_attempt_id", None)
        return safe

    @classmethod
    def to_worker_dict(cls, job: dict) -> dict:
        if not job:
            return None
        safe = dict(job)
        safe.pop("view_token", None)
        return safe

    @classmethod
    def to_admin_dict(cls, job: dict) -> dict:
        if not job:
            return None
        return dict(job)

    @classmethod
    def clear_llm_waiting_state(cls, pipeline_state: dict, extra_updates: dict = None):
        """Strips active LLM waiting metadata when escaping WAITING_FOR_LLM_CAPACITY."""
        if "llm_waiting_state" in pipeline_state:
            pipeline_state["llm_waiting_state"] = False
        if "next_retry" in pipeline_state:
            pipeline_state["next_retry"] = None
        if extra_updates is not None and "next_retry" not in extra_updates:
            extra_updates["next_retry"] = None

    @classmethod
    def validate_state_consistency(cls, cursor, task_id: str, status: str, pipeline_state: dict):
        if pipeline_state is None:
            return
            
        awaiting_approval = pipeline_state.get("awaiting_approval")
        approval_state = pipeline_state.get("approval_state")
        llm_waiting_state = pipeline_state.get("llm_waiting_state")

        if status == "WAITING_FOR_APPROVAL":
            if not awaiting_approval:
                raise ValueError("Inconsistent state: WAITING_FOR_APPROVAL requires awaiting_approval=True")
            if approval_state != "pending":
                raise ValueError("Inconsistent state: WAITING_FOR_APPROVAL requires approval_state='pending'")
            cycle_id = pipeline_state.get("approval_cycle_id")
            if not cycle_id:
                raise ValueError("Inconsistent state: WAITING_FOR_APPROVAL requires approval_cycle_id")
            payload = pipeline_state.get("approval_payload")
            if payload is None:
                raise ValueError("Inconsistent state: WAITING_FOR_APPROVAL requires approval_payload")
            fix_id = payload.get("fix_id")
            if not fix_id:
                raise ValueError("Inconsistent state: WAITING_FOR_APPROVAL requires approval_payload.fix_id")
                
            repair_plan = pipeline_state.get("repair_plan", [])
            plan_fix = next((f for f in repair_plan if f.get("fix_id") == fix_id), None)
            if not plan_fix:
                raise ValueError("Inconsistent state: WAITING_FOR_APPROVAL requires fix_id in repair_plan")
            if plan_fix.get("status") != "pending":
                raise ValueError("Inconsistent state: WAITING_FOR_APPROVAL requires repair_plan target fix status to be pending")
                
            if cursor:
                cursor.execute(
                    "SELECT credential_id, approval_cycle_id, fix_id FROM approval_credentials WHERE task_id = ? AND status = 'active'",
                    (task_id,)
                )
                active_cred = cursor.fetchone()
                if active_cred:
                    cred_id, cred_cycle, cred_fix = active_cred
                    if cred_cycle != cycle_id:
                        raise ValueError("Inconsistent state: Active credential cycle_id does not match pipeline_state")
                    if cred_fix != fix_id:
                        raise ValueError("Inconsistent state: Active credential fix_id does not match pipeline_state")

        elif status == "RUNNING":
            if awaiting_approval:
                raise ValueError("Inconsistent state: RUNNING cannot claim awaiting_approval=True")
            if approval_state == "pending":
                raise ValueError("Inconsistent state: RUNNING cannot claim approval_state='pending'")
            if llm_waiting_state:
                raise ValueError("Inconsistent state: RUNNING cannot claim llm_waiting_state=True")
            if pipeline_state.get("next_retry"):
                raise ValueError("Inconsistent state: RUNNING cannot claim active next_retry")
                
        elif status == "DISPATCHING":
            if llm_waiting_state:
                raise ValueError("Inconsistent state: DISPATCHING cannot claim llm_waiting_state=True")
            if pipeline_state.get("next_retry"):
                raise ValueError("Inconsistent state: DISPATCHING cannot claim active next_retry")

        elif status == "WAITING_FOR_DISPATCH":
            if awaiting_approval:
                raise ValueError("Inconsistent state: WAITING_FOR_DISPATCH cannot claim awaiting_approval=True")
            if approval_state == "pending":
                raise ValueError("Inconsistent state: WAITING_FOR_DISPATCH cannot claim approval_state='pending'")
                
        elif status == "WAITING_FOR_LLM_CAPACITY":
            if not llm_waiting_state:
                raise ValueError("Inconsistent state: WAITING_FOR_LLM_CAPACITY requires llm_waiting_state=True")
                
            next_retry = pipeline_state.get("next_retry")
            if not next_retry:
                raise ValueError("Inconsistent state: WAITING_FOR_LLM_CAPACITY requires next_retry")
                
            _, is_malformed = cls._check_llm_cooldown(next_retry)
            if is_malformed:
                raise ValueError("Inconsistent state: next_retry is malformed or invalid absolute UTC timestamp")
                
                
                
        elif status in ("COMPLETED", "FAILED", "NEEDS_REVIEW"):
            if awaiting_approval:
                raise ValueError("Inconsistent state: Terminal state cannot claim awaiting_approval=True")
            if llm_waiting_state:
                raise ValueError("Inconsistent state: Terminal state cannot claim llm_waiting_state=True")

    @classmethod
    def save_worker_state(cls, task_id: str, worker_attempt_id: str, status: str, pipeline_state: dict) -> bool:
        if not worker_attempt_id:
            raise ValueError("worker_attempt_id is required for external worker state updates")
            
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            conn.transaction()
            cursor.execute("SELECT status, worker_attempt_id FROM jobs WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Task not found")
                
            current_status, current_attempt = row
            if worker_attempt_id != current_attempt:
                raise ValueError("Stale worker attempt")
                
            if current_status == "WAITING_FOR_APPROVAL":
                raise ValueError("Worker state persistence is forbidden while human approval is pending")
                
            if current_status == status:
                cls.validate_state_consistency(cursor, task_id, status, pipeline_state)
                cursor.execute(
                    "UPDATE jobs SET pipeline_state = ?, updated_at = ? WHERE task_id = ? AND worker_attempt_id = ?",
                    (json.dumps(pipeline_state), now, task_id, worker_attempt_id)
                )
                if cursor.rowcount == 0:
                    raise ValueError("Stale worker attempt during update")
                success = True
            else:
                cls.transition_job_state(
                    cursor=cursor,
                    task_id=task_id,
                    target_status=status,
                    worker_attempt_id=worker_attempt_id,
                    enforce_worker_fencing=True,
                    pipeline_state=pipeline_state,
                    timestamp=now
                )
            conn.commit()
            success = True
        except ValueError as e:
            conn.rollback()
            raise e
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            
        return success

    @classmethod
    def claim_waiting_job(cls, task_id: str) -> Optional[str]:
        """Atomically transitions a job to DISPATCHING. Returns worker_attempt_id if claimed, else None."""
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.transaction()
            cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT status, dispatch_count, next_retry FROM jobs WHERE task_id = ?"), (task_id,))
            row = cursor.fetchone()
            if row:
                status, dispatch_count, next_retry = row
                dispatch_count = dispatch_count or 0
                
                can_claim = False
                if status == "WAITING_FOR_DISPATCH":
                    can_claim = True
                elif status == "WAITING_FOR_LLM_CAPACITY":
                    can_claim, is_malformed = cls._check_llm_cooldown(next_retry)
                    if is_malformed:
                        if cls._is_valid_transition(status, "NEEDS_REVIEW"):
                            cls.transition_job_state(cursor, task_id, "NEEDS_REVIEW", timestamp=now)
                            conn.commit()
                        return None

                if can_claim:
                    if dispatch_count >= 3:
                        if cls._is_valid_transition(status, "FAILED"):
                            cls.transition_job_state(cursor, task_id, "FAILED", timestamp=now)
                            conn.commit()
                        return None
                    
                    if not cls._is_valid_transition(status, "DISPATCHING"):
                        # Ensure we don't dispatch an invalid state
                        conn.rollback()
                        return None
                        
                    import uuid
                    worker_attempt_id = str(uuid.uuid4())
                    
                    extra_updates = {
                        "dispatch_attempted_at": now,
                        "dispatch_count": dispatch_count + 1,
                        "worker_attempt_id": worker_attempt_id,
                        "worker_started_at": now,
                        "worker_heartbeat_at": now
                    }
                    
                    event_data = {
                        "worker_attempt_id": worker_attempt_id,
                        "dispatch_count": dispatch_count + 1,
                        "source": "claim"
                    }
                    success, seq = cls.transition_job_state(
                        cursor, 
                        task_id, 
                        "DISPATCHING", 
                        extra_updates=extra_updates, 
                        timestamp=now,
                        event_name="dispatch",
                        event_data=event_data
                    )
                    conn.commit()
                    
                    try:
                        cls._broadcast_event(task_id, "dispatch", event_data, "DISPATCHING", seq, now)
                    except Exception as e:
                        print(f"Warning: Failed to broadcast dispatch event for task {task_id}: {e}")
                        
                    return worker_attempt_id
            conn.rollback()
            return None
        except Exception as e:
            print(f"Error in claim_waiting_job: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    @classmethod
    def recover_stale_worker_claim(cls, task_id: str) -> Optional[str]:
        """Atomically recovers a stale RUNNING or DISPATCHING job, transitions it to DISPATCHING, and issues a new worker claim."""
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.transaction()
            cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT status, dispatch_count, worker_heartbeat_at, dispatch_attempted_at, worker_attempt_id, pipeline_state FROM jobs WHERE task_id = ?"), (task_id,))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return None
                
            status, dispatch_count, hb_at, dispatch_at, current_attempt, p_state_str = row
            dispatch_count = dispatch_count or 0
            
            if status not in ("DISPATCHING", "RUNNING"):
                conn.rollback()
                return None
                
            current_ts = datetime.now(timezone.utc).timestamp()
            stale = False
            
            if hb_at:
                try:
                    if not isinstance(hb_at, str) and hb_at.tzinfo is None:
                        hb_at = hb_at.replace(tzinfo=timezone.utc)
                    hb_ts = (hb_at.timestamp() if not isinstance(hb_at, str) else datetime.fromisoformat(hb_at.replace("Z", "+00:00")).timestamp())
                    if current_ts - hb_ts > 300:
                        stale = True
                except ValueError as e:
                    print(f"Warning: Invalid heartbeat timestamp: {e}")
                    stale = True
            elif dispatch_at:
                try:
                    if not isinstance(dispatch_at, str) and dispatch_at.tzinfo is None:
                        dispatch_at = dispatch_at.replace(tzinfo=timezone.utc)
                    disp_ts = (dispatch_at.timestamp() if not isinstance(dispatch_at, str) else datetime.fromisoformat(dispatch_at.replace("Z", "+00:00")).timestamp())
                    if current_ts - disp_ts > 300:
                        stale = True
                except ValueError as e:
                    print(f"Warning: Invalid dispatch timestamp: {e}")
                    stale = True
            else:
                stale = True
                
            if not stale:
                conn.rollback()
                return None
                
            if dispatch_count >= 3:
                if cls._is_valid_transition(status, "FAILED"):
                    cls.transition_job_state(cursor, task_id, "FAILED", timestamp=now)
                    conn.commit()
                return None
                
            import uuid
            worker_attempt_id = str(uuid.uuid4())
            
            extra_updates = {
                "dispatch_attempted_at": now,
                "dispatch_count": dispatch_count + 1,
                "worker_attempt_id": worker_attempt_id,
                "worker_started_at": now,
                "worker_heartbeat_at": now
            }
            
            event_data = {"reason": "stale_attempt"}
            
            # Perform transition natively since STALE_WORKER_RECOVERY bypass is removed from normal transitions
            import json
            pipeline_state = {}
            if p_state_str:
                try:
                    pipeline_state = json.loads(p_state_str)
                except Exception:
                    pass
            
            if status == "WAITING_FOR_APPROVAL":
                conn.rollback()
                return None
                
            cls.clear_llm_waiting_state(pipeline_state)
            cls.validate_state_consistency(cursor, task_id, "DISPATCHING", pipeline_state)
            
            update_fields = [
                "status = ?", 
                "updated_at = ?", 
                "dispatch_attempted_at = ?",
                "dispatch_count = ?",
                "worker_attempt_id = ?",
                "worker_started_at = ?",
                "worker_heartbeat_at = ?",
                "pipeline_state = ?"
            ]
            update_values = [
                "DISPATCHING",
                now,
                now,
                dispatch_count + 1,
                worker_attempt_id,
                now,
                now,
                json.dumps(pipeline_state),
                task_id,
                current_attempt
            ]
            
            if current_attempt is None:
                update_values_no_attempt = list(update_values)
                update_values_no_attempt.pop() # remove current_attempt
                cursor.execute(f"UPDATE jobs SET {', '.join(update_fields)} WHERE task_id = ? AND worker_attempt_id IS NULL", tuple(update_values_no_attempt))
            else:
                cursor.execute(f"UPDATE jobs SET {', '.join(update_fields)} WHERE task_id = ? AND worker_attempt_id = ?", tuple(update_values))
                
            if cursor.rowcount == 0:
                conn.rollback()
                return None

            
            cursor.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE task_id = ?", (task_id,))
            seq = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT INTO job_events (task_id, sequence, status, event_name, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, seq, "DISPATCHING", "worker_revoked", json.dumps(event_data), now)
            )
            
            conn.commit()
            cls._broadcast_event(task_id, "worker_revoked", event_data, "DISPATCHING", seq, now)
            return worker_attempt_id
        except Exception as e:
            print(f"Error in recover_stale_worker_claim: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    @classmethod
    def record_dispatch_failure(cls, task_id: str, error: str, worker_attempt_id: str = None):
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        import datetime as dt
        next_retry = (now + dt.timedelta(minutes=5)).isoformat()
        try:
            conn.transaction()
            cursor.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Task not found")
                
            current_status = row[0]
            if current_status != "DISPATCHING":
                raise ValueError(f"Cannot record dispatch failure from status: {current_status}")
                
            extra_updates = {
                "next_retry": next_retry,
                "last_dispatch_error": error,
                "worker_attempt_id": None,
                "worker_started_at": None,
                "worker_heartbeat_at": None
            }
            cls.transition_job_state(
                cursor=cursor,
                task_id=task_id,
                target_status="WAITING_FOR_DISPATCH",
                worker_attempt_id=worker_attempt_id,
                enforce_worker_fencing=bool(worker_attempt_id),
                extra_updates=extra_updates,
                timestamp=now.isoformat(),
                event_name="dispatch_failed",
                event_data={"error": error}
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Warning: Failed to record dispatch failure: {e}")
        finally:
            conn.close()

    @classmethod
    def set_worker_waiting_capacity(cls, task_id: str, worker_attempt_id: str, next_retry_timestamp: str, pipeline_state: dict = None) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            conn.transaction()
            cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT status, pipeline_state FROM jobs WHERE task_id = ?"), (task_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Task not found")
            current_status = row[0]
            
            if not cls._is_valid_transition(current_status, "WAITING_FOR_LLM_CAPACITY"):
                raise ValueError(f"Invalid state transition: {current_status} -> WAITING_FOR_LLM_CAPACITY")
                
            import copy
            if pipeline_state:
                state = copy.deepcopy(pipeline_state)
            else:
                state = {}
                if row and row[1]:
                    state = json.loads(row[1])
                
            state["status"] = "WAITING_FOR_LLM_CAPACITY"
            state["next_retry"] = next_retry_timestamp
            state["llm_waiting_state"] = True
            
            error_msg = state.get("pr_error", "LLM Capacity Exhausted")
            event_data = {
                "error": error_msg,
                "retry_count": state.get("retry_count"),
                "next_retry": state.get("next_retry"),
                "model": state.get("last_llm_model"),
                "reset_time": None,
                "last_error": state.get("last_llm_error"),
                "status": "WAITING_FOR_LLM_CAPACITY"
            }
            
            extra_updates = {"next_retry": next_retry_timestamp}
            
            success, sequence = cls.transition_job_state(
                cursor=cursor,
                task_id=task_id,
                target_status="WAITING_FOR_LLM_CAPACITY",
                worker_attempt_id=worker_attempt_id,
                enforce_worker_fencing=True,
                pipeline_state=state,
                event_name="waiting_for_llm_capacity",
                event_data=event_data,
                timestamp=now,
                extra_updates=extra_updates
            )
            
            conn.commit()
            
            if success:
                cls._broadcast_event(task_id, "waiting_for_llm_capacity", event_data, "WAITING_FOR_LLM_CAPACITY", sequence, now)
                
            return success
        except Exception as e:
            conn.rollback()
            print(f"Error in set_worker_waiting_capacity: {e}")
            return False
        finally:
            conn.close()

    @classmethod
    def resolve_approval(cls, task_id: str, decision: str, hashed_token: str, fix_id: str, approval_cycle_id: str) -> dict:
        """Atomically resolves an approval and emits a broadcast event."""
        import hmac
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        now_ts = datetime.now(timezone.utc).timestamp()
        
        try:
            conn.transaction()
            p_state_str, current_worker_id, cred_row = cls.validate_approval_context(cursor, task_id, approval_cycle_id, fix_id)
            credential_id, cred_worker_id, db_token, expires_at = cred_row
            
            if not db_token or not hmac.compare_digest(db_token, hashed_token):
                raise ValueError("Invalid approval_token")

            if expires_at:
                try:
                    if not isinstance(expires_at, str) and expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    expires = (expires_at.timestamp() if not isinstance(expires_at, str) else datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp())
                    if now_ts > expires:
                        raise ValueError("Approval token expired")
                except ValueError as e:
                    print(f"Warning: Invalid approval token expiry timestamp: {e}")
                    raise ValueError("Approval token expired")

            try:
                p_state = json.loads(p_state_str) if p_state_str else {}
            except json.JSONDecodeError:
                p_state = {}

            state_cycle_id = p_state.get("approval_cycle_id")
            if state_cycle_id != approval_cycle_id:
                raise ValueError("Approval cycle ID does not match current pending approval")

            payload = p_state.get("approval_payload")
            if not payload:
                raise ValueError("No approval payload found in state")

            state_fix_id = payload.get("fix_id")
            if not state_fix_id or fix_id != state_fix_id:
                raise ValueError(f"State fix_id mismatch. Expected {state_fix_id}, got {fix_id}")

            # Update repair_plan inside the state
            repair_plan = p_state.get("repair_plan", [])
            fix_found = False
            for fix in repair_plan:
                if fix.get("fix_id") == fix_id:
                    if fix.get("status") != "pending":
                        raise ValueError(f"Repair fix {fix_id} is not in pending status")
                    fix["status"] = decision
                    fix_found = True
                    break
                    
            if not fix_found:
                raise ValueError(f"Repair fix {fix_id} not found in repair plan")
                    
            new_status = "WAITING_FOR_DISPATCH" if decision == "approved" else "NEEDS_REVIEW"
            
            p_state["awaiting_approval"] = False
            p_state["approval_decision"] = decision
            p_state["approval_state"] = decision
            p_state.pop("approval_cycle_id", None)
            
            # Pop the payload and append to history
            payload = p_state.pop("approval_payload", None)
            if payload:
                p_state.setdefault("resolved_approvals", []).append({
                    "approval_cycle_id": approval_cycle_id,
                    "fix_id": fix_id,
                    "decision": decision,
                    "payload": payload,
                    "timestamp": now
                })
            p_state["current_fix"] = None

            # Mark credential as used
            cursor.execute(
                "UPDATE approval_credentials SET status = 'used', used_at = ?, decision = ? WHERE approval_cycle_id = ? AND token_hash = ?",
                (now, decision, approval_cycle_id, hashed_token)
            )
            
            cls.validate_state_consistency(cursor, task_id, new_status, p_state)
            
            event_name = "approval_resolved"
            data = {
                "decision": decision,
                "status": new_status,
                "approval_state": decision,
                "awaiting_approval": False,
                "approval_payload": None,
                "fix_id": fix_id,
                "approval_cycle_id": approval_cycle_id
            }
            
            extra_updates = {
                "approval_decision": decision,
                "dispatch_count": 0
            }
            
            success, sequence = cls.transition_job_state(
                cursor=cursor,
                task_id=task_id,
                target_status=new_status,
                enforce_worker_fencing=False,
                pipeline_state=p_state,
                event_name=event_name,
                event_data=data,
                timestamp=now,
                extra_updates=extra_updates
            )
            
            conn.commit()
            success = True
        except ValueError as e:
            conn.rollback()
            raise e
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Internal error during approval: {str(e)}")
        finally:
            conn.close()
            
        if success:
            cls._broadcast_event(task_id, event_name, data, new_status, sequence, now)

        return {
            "status": new_status,
            "decision": decision,
            "approval_state": decision,
            "awaiting_approval": False,
            "current_fix": None,
            "timestamp": now,
            "sequence": sequence
        }

    @classmethod
    def get_waiting_jobs_ready(cls) -> List[dict]:
        """Fetch jobs that are ready to be dispatched or recovered (atomic race-free check)."""
        conn = get_connection()
        cursor = conn.cursor()
        ready_jobs = []
        
        now = datetime.now(timezone.utc).timestamp()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        try:
            conn.transaction()
            cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT task_id, repo_url, status, commit_sha, dispatch_attempted_at, worker_heartbeat_at, next_retry FROM jobs WHERE status IN ('WAITING_FOR_LLM_CAPACITY', 'WAITING_FOR_DISPATCH', 'DISPATCHING', 'RUNNING')"))
            rows = cursor.fetchall()
            
            for task_id, repo_url, status, commit_sha, dispatch_attempted_at, worker_heartbeat_at, next_retry in rows:
                if status == "WAITING_FOR_DISPATCH":
                    if next_retry:
                        can_claim, is_malformed = cls._check_llm_cooldown(next_retry)
                        if is_malformed:
                            cls.transition_job_state(
                                cursor,
                                task_id,
                                "NEEDS_REVIEW",
                                timestamp=now_iso,
                                event_name="scheduler_state_invalid",
                                event_data={"reason": "malformed_next_retry"}
                            )
                            continue
                        if not can_claim:
                            continue
                
                    ready_jobs.append({
                        "task_id": task_id,
                        "repo_url": repo_url,
                        "commit_sha": commit_sha or "",
                        "status": status
                    })
                elif status in ("DISPATCHING", "RUNNING"):
                    stale = False
                    if worker_heartbeat_at:
                        try:
                            hb_time = (worker_heartbeat_at.timestamp() if not isinstance(worker_heartbeat_at, str) else datetime.fromisoformat(worker_heartbeat_at.replace("Z", "+00:00")).timestamp())
                            if now - hb_time > 300: # 5 minutes
                                stale = True
                        except Exception as e:
                            print(f"Warning: heartbeat parsing failed: {e}")
                            stale = True
                    elif dispatch_attempted_at:
                        try:
                            attempted_time = (dispatch_attempted_at.timestamp() if not isinstance(dispatch_attempted_at, str) else datetime.fromisoformat(dispatch_attempted_at.replace("Z", "+00:00")).timestamp())
                            if now - attempted_time > 300:
                                stale = True
                        except Exception as e:
                            print(f"Warning: dispatch_attempted_at parsing failed: {e}")
                            stale = True
                    else:
                        stale = True
    
                    if stale:
                        ready_jobs.append({
                            "task_id": task_id,
                            "repo_url": repo_url,
                            "commit_sha": commit_sha or "",
                            "status": status
                        })
    
                elif status == "WAITING_FOR_LLM_CAPACITY":
                    can_claim, is_malformed = cls._check_llm_cooldown(next_retry)
                    if is_malformed:
                        cls.transition_job_state(
                            cursor,
                            task_id,
                            "NEEDS_REVIEW",
                            timestamp=now_iso,
                            event_name="scheduler_state_invalid",
                            event_data={"reason": "malformed_next_retry"}
                        )
                        continue
                    if can_claim:
                        ready_jobs.append({
                            "task_id": task_id,
                            "repo_url": repo_url,
                            "commit_sha": commit_sha or "",
                            "status": status
                        })
                        
            conn.commit()
            return ready_jobs
        except Exception as e:
            conn.rollback()
            print(f"Error in get_waiting_jobs_ready: {e}")
            return []
        finally:
            conn.close()

    @classmethod
    def get_latest_sequence(cls, task_id: str) -> int:
        """Returns the latest sequence number for the given task_id, or 0 if none exist."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(sequence) FROM job_events WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            conn.close()
            if row and row[0] is not None:
                return row[0]
            return 0
        except Exception as e:
            print(f"Error: Failed to fetch latest sequence for {task_id}: {e}")
            raise RuntimeError(f"Database error fetching sequence: {e}")

    @classmethod
    def get_events(cls, task_id: str, since_sequence: int = -1) -> List[dict]:
        """Fetch historical events, useful for reconnection."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sequence, status, event_name, data, timestamp FROM job_events WHERE task_id = ? AND sequence > ? ORDER BY sequence ASC",
            (task_id, since_sequence),
        )
        rows = cursor.fetchall()
        conn.close()

        events = []
        for r in rows:
            events.append(
                {
                    "sequence": r[0],
                    "status": r[1],
                    "event": r[2],
                    "data": json.loads(r[3]),
                    "timestamp": r[4],
                }
            )
        return events

    @classmethod
    def subscribe(cls, task_id: str) -> asyncio.Queue:
        if task_id not in cls._live_queues:
            cls._live_queues[task_id] = []
        q = asyncio.Queue()
        cls._live_queues[task_id].append(q)
        return q

    @classmethod
    def unsubscribe(cls, task_id: str, q: asyncio.Queue):
        if task_id in cls._live_queues:
            if q in cls._live_queues[task_id]:
                cls._live_queues[task_id].remove(q)
            if len(cls._live_queues[task_id]) == 0:
                del cls._live_queues[task_id]

    @classmethod
    def create_admin_session(cls) -> str:
        session_id = secrets.token_urlsafe(32)
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        expires = datetime.fromtimestamp(now.timestamp() + 3600, tz=timezone.utc)
        cursor.execute(
            "INSERT INTO admin_sessions (session_id, created_at, expires_at) VALUES (?, ?, ?)",
            (session_id, now.isoformat(), expires.isoformat())
        )
        conn.commit()
        conn.close()
        return session_id

    @classmethod
    def validate_admin_session(cls, session_id: str) -> bool:
        if not session_id:
            return False
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "SELECT expires_at FROM admin_sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return False
            
        expires_at = row[0]
        if now > expires_at:
            # Lazy cleanup
            cursor.execute("DELETE FROM admin_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()
            return False
            
        conn.close()
        return True

    @classmethod
    def delete_admin_session(cls, session_id: str):
        if not session_id:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM admin_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

    @classmethod
    def get_pipeline_health_metrics(cls) -> dict:
        conn = get_connection()
        cursor = conn.cursor()
        
        import datetime as dt
        active_threshold = (datetime.now(timezone.utc) - dt.timedelta(hours=24)).isoformat()
        
        cursor.execute("SELECT status, count(*), sum(case when updated_at > ? then 1 else 0 end) FROM jobs GROUP BY status", (active_threshold,))
        rows = cursor.fetchall()
        conn.close()
        
        # Initialize all 11 explicit distinct states
        metrics = {
            "queued": 0,
            "starting": 0,
            "running": 0,
            "dispatching": 0,
            "waiting for dispatch": 0,
            "waiting for approval": 0,
            "waiting for llm capacity": 0,
            "retrying": 0,
            "completed": 0,
            "needs review": 0,
            "failed": 0,
            "active_failed": 0
        }
        
        for status, count, active_count in rows:
            active_count = active_count or 0
            if status == "QUEUED": metrics["queued"] = count
            elif status == "STARTING": metrics["starting"] = count
            elif status == "RUNNING" or status == "RESUMING": metrics["running"] += count
            elif status == "DISPATCHING": metrics["dispatching"] = count
            elif status == "WAITING_FOR_DISPATCH": metrics["waiting for dispatch"] = count
            elif status == "WAITING_FOR_APPROVAL": metrics["waiting for approval"] = count
            elif status == "WAITING_FOR_LLM_CAPACITY": metrics["waiting for llm capacity"] = count
            elif status == "RETRYING": metrics["retrying"] = count
            elif status == "COMPLETED": metrics["completed"] = count
            elif status == "NEEDS_REVIEW": metrics["needs review"] = count
            elif status == "FAILED": 
                metrics["failed"] = count
                metrics["active_failed"] = active_count
            
        return metrics

    @classmethod
    def create_sse_capability(cls, task_id: str) -> str:
        token = secrets.token_hex(32)
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        # Capability expires in 5 minutes
        expires = datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc)
        
        cursor.execute("DELETE FROM sse_capabilities WHERE expires_at < ?", (now.isoformat(),))
        
        cursor.execute(
            "INSERT INTO sse_capabilities (token, task_id, expires_at) VALUES (?, ?, ?)",
            (token, task_id, expires.isoformat())
        )
        conn.commit()
        conn.close()
        return token

    @classmethod
    def validate_sse_capability(cls, token: str, task_id: str) -> bool:
        if not token or not task_id:
            return False
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "SELECT expires_at FROM sse_capabilities WHERE token = ? AND task_id = ?",
            (token, task_id)
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return False
            
        expires_at = row[0]
        # Single use capability: delete it immediately
        cursor.execute("DELETE FROM sse_capabilities WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        
        if now > expires_at:
            return False
            
        return True
