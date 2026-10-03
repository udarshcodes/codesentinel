import os
import json
import hmac
import hashlib
import httpx
from datetime import datetime, timezone

TASK_ID = os.environ.get("TASK_ID")
BACKEND_URL = os.environ.get("BACKEND_URL")
WORKER_SECRET = os.environ.get("WORKER_WEBHOOK_SECRET", "")
WORKER_ATTEMPT_ID = os.environ.get("WORKER_ATTEMPT_ID", "")
COMMIT_SHA = os.environ.get("COMMIT_SHA", "")
REPO_URL = os.environ.get("REPO_URL", "")

async def authenticated_post(path: str, json_payload: dict):
    """Post to backend with HMAC replay protection signature."""
    headers = {
        "X-Worker-Attempt-Id": WORKER_ATTEMPT_ID,
        "X-Repo-Url": REPO_URL
    }
    if COMMIT_SHA:
        headers["X-Commit-Sha"] = COMMIT_SHA

    timestamp = str(datetime.now(timezone.utc).timestamp())
    body_bytes = json.dumps(json_payload, separators=(',', ':')).encode('utf-8')
    
    if WORKER_SECRET:
        msg = f"POST:{path}:{TASK_ID}:{timestamp}:{WORKER_ATTEMPT_ID}:{COMMIT_SHA}:{REPO_URL}:".encode() + body_bytes
        sig = "sha256=" + hmac.HMAC(WORKER_SECRET.encode(), msg, hashlib.sha256).hexdigest()
        headers["X-Worker-Signature"] = sig
        headers["X-Timestamp"] = timestamp

    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient() as client:
        return await client.post(
            f"{BACKEND_URL}{path}", content=body_bytes, headers=headers, timeout=10.0
        )

async def authenticated_get(path: str):
    """Get from backend with HMAC replay protection signature."""
    headers = {
        "X-Worker-Attempt-Id": WORKER_ATTEMPT_ID,
        "X-Repo-Url": REPO_URL
    }
    if COMMIT_SHA:
        headers["X-Commit-Sha"] = COMMIT_SHA

    timestamp = str(datetime.now(timezone.utc).timestamp())
    
    if WORKER_SECRET:
        msg = f"GET:{path}:{TASK_ID}:{timestamp}:{WORKER_ATTEMPT_ID}:{COMMIT_SHA}:{REPO_URL}:".encode() + b""
        sig = "sha256=" + hmac.HMAC(WORKER_SECRET.encode(), msg, hashlib.sha256).hexdigest()
        headers["X-Worker-Signature"] = sig
        headers["X-Timestamp"] = timestamp

    async with httpx.AsyncClient() as client:
        return await client.get(
            f"{BACKEND_URL}{path}", headers=headers, timeout=10.0
        )

_LEASE_LOST = False

def is_lease_lost() -> bool:
    return _LEASE_LOST

def abort_lease():
    global _LEASE_LOST
    _LEASE_LOST = True
