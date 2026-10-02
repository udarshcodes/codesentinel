import os
import hmac
import hashlib
from datetime import datetime, timezone
from fastapi import Request, HTTPException

async def verify_worker_signature(request: Request, task_id: str) -> bytes:
    """
    Verifies the worker's HMAC signature.
    Returns the request body bytes if valid, raises HTTPException otherwise.
    """
    worker_secret = os.getenv("WORKER_WEBHOOK_SECRET", "")
    environment = os.getenv("ENVIRONMENT", "development")
    bypass = os.getenv("WORKER_AUTH_BYPASS", "").lower() == "true"
    
    if environment == "production" and bypass:
        raise HTTPException(status_code=500, detail="Configuration Error: WORKER_AUTH_BYPASS must never be true in production")
        
    if not worker_secret:
        if bypass and environment != "production":
            return await request.body()
        raise HTTPException(status_code=500, detail="Configuration Error: WORKER_WEBHOOK_SECRET missing")

    signature_header = request.headers.get("X-Worker-Signature", "")
    if not signature_header:
        raise HTTPException(status_code=403, detail="Missing X-Worker-Signature header")

    timestamp = request.headers.get("X-Timestamp", "")
    if not timestamp:
        raise HTTPException(status_code=403, detail="Missing X-Timestamp header")

    try:
        event_time = float(timestamp)
        now = datetime.now(timezone.utc).timestamp()
        if abs(now - event_time) > 300:
            raise HTTPException(status_code=403, detail="Expired timestamp (replay protection)")
    except ValueError:
        raise HTTPException(status_code=403, detail="Malformed timestamp (replay protection)")

    body_bytes = await request.body()
    
    worker_attempt_id = request.headers.get("X-Worker-Attempt-Id", "")
    commit_sha = request.headers.get("X-Commit-Sha", "")
    repo_url = request.headers.get("X-Repo-Url", "")
    
    # Signature formulation: METHOD:PATH:TASK_ID:TIMESTAMP:ATTEMPT_ID:COMMIT_SHA:REPO_URL:BODY
    msg = f"{request.method}:{request.url.path}:{task_id}:{timestamp}:{worker_attempt_id}:{commit_sha}:{repo_url}:".encode() + body_bytes
    expected_sig = "sha256=" + hmac.HMAC(worker_secret.encode(), msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_sig, signature_header):
        raise HTTPException(status_code=403, detail="Invalid worker signature")
        
    return body_bytes

async def validate_worker_attempt(request: Request, task_id: str) -> dict:
    """
    Centralized validation for worker endpoints.
    Verifies HMAC, requires worker attempt ID, and checks authoritative state.
    Returns the job dict if valid.
    """
    await verify_worker_signature(request, task_id)
    
    worker_attempt_id = request.headers.get("X-Worker-Attempt-Id")
    if not worker_attempt_id:
        raise HTTPException(status_code=400, detail="Missing X-Worker-Attempt-Id header")

    from api.job_manager import JobManager
    job = JobManager.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("worker_attempt_id") != worker_attempt_id:
        raise HTTPException(status_code=409, detail="Stale worker attempt")
        
    commit_sha = request.headers.get("X-Commit-Sha")
    if commit_sha and job.get("commit_sha") and commit_sha != job.get("commit_sha"):
        raise HTTPException(status_code=409, detail="Worker commit_sha mismatch")

    repo_url = request.headers.get("X-Repo-Url")
    if not repo_url:
        raise HTTPException(status_code=400, detail="Missing X-Repo-Url header")
    if repo_url != job.get("repo_url"):
        raise HTTPException(status_code=409, detail="Worker repo_url mismatch")

    # Verify task is still worker owned
    if job.get("status") not in ("DISPATCHING", "STARTING", "RUNNING", "WAITING_FOR_LLM_CAPACITY", "WAITING_FOR_APPROVAL"):
        raise HTTPException(status_code=409, detail=f"Task is no longer worker owned, status: {job.get('status')}")

    return job
