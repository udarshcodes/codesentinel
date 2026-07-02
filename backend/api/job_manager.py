import sqlite3
import json
import os
from datetime import datetime
import asyncio
from typing import Optional, List, Dict, Any

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "codesentinel.db"))

def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    # Track overall job status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            task_id TEXT PRIMARY KEY,
            repo_url TEXT,
            status TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    # Track granular idempotent events for SSE streaming
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            sequence INTEGER,
            status TEXT,
            event_name TEXT,
            data TEXT,
            timestamp TIMESTAMP,
            UNIQUE(task_id, sequence)
        )
    """)
    conn.commit()
    conn.close()

# Initialize on module load
init_db()

class JobManager:
    # Explicit state machine states
    QUEUED = "QUEUED"
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

    # In-memory asyncio queues for real-time SSE streaming (per task_id)
    # This prevents needing to poll the database constantly.
    # When a new event arrives, it is saved to DB and then pushed to the queue.
    _live_queues: Dict[str, List[asyncio.Queue]] = {}

    @classmethod
    def create_job(cls, task_id: str, repo_url: str):
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO jobs (task_id, repo_url, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, repo_url, cls.QUEUED, now, now)
        )
        conn.commit()
        conn.close()

    @classmethod
    def add_event(cls, task_id: str, sequence: int, status: str, event_name: str, data: dict, timestamp: str) -> bool:
        """
        Adds an idempotent event. Returns True if inserted, False if duplicate sequence.
        """
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO job_events (task_id, sequence, status, event_name, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, sequence, status, event_name, json.dumps(data), timestamp)
            )
            
            # Update the latest status in jobs table
            cursor.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, timestamp, task_id)
            )
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            # Duplicate sequence for this task_id. Idempotency guarantees we ignore it safely.
            success = False
        finally:
            conn.close()

        # If it was a new event, push to any active live SSE subscribers
        if success and task_id in cls._live_queues:
            event_payload = {
                "event": event_name,
                "data": data,
                "status": status,
                "sequence": sequence,
                "timestamp": timestamp
            }
            for q in cls._live_queues[task_id]:
                try:
                    q.put_nowait(event_payload)
                except asyncio.QueueFull:
                    pass
                    
        return success

    @classmethod
    def get_job(cls, task_id: str) -> Optional[dict]:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, repo_url, status, created_at, updated_at FROM jobs WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "task_id": row[0],
                "repo_url": row[1],
                "status": row[2],
                "created_at": row[3],
                "updated_at": row[4]
            }
        return None

    @classmethod
    def get_events(cls, task_id: str, after_sequence: int = -1) -> List[dict]:
        """Fetch historical events, useful for reconnection."""
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sequence, status, event_name, data, timestamp FROM job_events WHERE task_id = ? AND sequence > ? ORDER BY sequence ASC",
            (task_id, after_sequence)
        )
        rows = cursor.fetchall()
        conn.close()
        
        events = []
        for r in rows:
            events.append({
                "sequence": r[0],
                "status": r[1],
                "event": r[2],
                "data": json.loads(r[3]),
                "timestamp": r[4]
            })
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
