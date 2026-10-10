from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, Cookie
from pydantic import BaseModel
import os
import re
import hmac
import hashlib
import httpx
import sqlite3
import uuid
import asyncio
from typing import Optional
from datetime import datetime, timezone
from state import broadcast_sse
from limiter import limiter
from api.job_manager import JobManager
from api.worker_auth import verify_worker_signature

router = APIRouter()


from typing import Literal

class AnalyzeRequest(BaseModel):
    repo_url: str
    commit_sha: str = None

class IssueApprovalTokenResponse(BaseModel):
    status: Literal["issued", "active"]
    task_id: str
    approval_cycle_id: str
    fix_id: str
    expires_at: str
    approval_token: Optional[str] = None

class RecoverCredentialResponse(BaseModel):
    status: Literal["recovered"]
    task_id: str
    approval_cycle_id: str
    fix_id: str
    expires_at: str
    approval_token: str


@router.post("/v1/analyze")
@router.post("/analyze")
@limiter.limit("2/minute")
async def start_analysis(
    request: Request, body: AnalyzeRequest, background_tasks: BackgroundTasks
):
    base_url = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https" and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://", 1)
    repo_url = body.repo_url.strip()
    if repo_url.startswith("github.com/"):
        repo_url = "https://" + repo_url
        body.repo_url = repo_url
    if not repo_url.endswith("/*"):
        if not re.match(
            r"^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:\.git)?$", repo_url
        ):
            raise HTTPException(
                400,
                "Invalid repository URL. Only GitHub HTTPS URLs are accepted (e.g., https://github.com/owner/repo).",
            )

    if body.commit_sha:
        if not re.match(r"^[a-fA-F0-9]{7,40}$", body.commit_sha):
            raise HTTPException(
                400, "commit_sha must be a valid 7-40 character hexadecimal Git object ID."
            )

    repos_to_analyze = [repo_url]

    # Handle Multi-Repository Mode (github.com/org/*)
    if repo_url.endswith("/*"):
        org_name = repo_url.split("github.com/")[-1].replace("/*", "")
        github_token = os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        fetched_repos = []
        try:
            async with httpx.AsyncClient() as client:
                url_to_fetch = f"https://api.github.com/orgs/{org_name}/repos?sort=updated&per_page=100"
                while url_to_fetch:
                    res = await client.get(url_to_fetch, headers=headers)
                    if res.status_code != 200:
                        url_to_fetch = f"https://api.github.com/users/{org_name}/repos?type=owner&sort=updated&per_page=100"
                        res = await client.get(url_to_fetch, headers=headers)
                        if res.status_code != 200:
                            break
                    
                    if res.status_code == 200:
                        repos = res.json()
                        fetched_repos.extend([
                            r["html_url"] for r in repos if not r.get("archived")
                        ])
                        
                        MAX_REPOS_PER_ANALYSIS_REQUEST = 10
                        if len(fetched_repos) > MAX_REPOS_PER_ANALYSIS_REQUEST:
                            raise HTTPException(
                                413, f"Organization wildcard exceeds maximum allowed repositories ({MAX_REPOS_PER_ANALYSIS_REQUEST})."
                            )
                        
                        # Check for pagination
                        link_header = res.headers.get("Link")
                        url_to_fetch = None
                        if link_header:
                            links = link_header.split(",")
                            for link in links:
                                if 'rel="next"' in link:
                                    url_to_fetch = link[link.find("<")+1:link.find(">")]
                                    break
        except HTTPException:
            raise
        except Exception as e:
            print(f"Warning: Error fetching org repos: {e}")

        if not fetched_repos:
            raise HTTPException(
                400,
                f"Could not find any active public repositories for organization/user '{org_name}'.",
            )
        repos_to_analyze = fetched_repos

    import secrets
    tasks = []
    
    async with httpx.AsyncClient() as client:
        github_token = os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
            
        for r_url in repos_to_analyze:
            task_id = str(uuid.uuid4())
            view_token = secrets.token_urlsafe(32)

            await asyncio.to_thread(JobManager.create_job, task_id, r_url, view_token, body.commit_sha)

            # Atomically claim the job for initial dispatch
            worker_attempt_id = await asyncio.to_thread(JobManager.claim_waiting_job, task_id)
            if not worker_attempt_id:
                print(f"Warning: Failed to claim newly created job {task_id}")
                continue

            background_tasks.add_task(
                trigger_github_worker, task_id, r_url, body.commit_sha, worker_attempt_id, base_url
            )
            
            tasks.append({
                "task_id": task_id,
                "repo_url": r_url,
                "view_token": view_token,
                "worker_attempt_id": worker_attempt_id
            })

    # For legacy backwards compatibility
    main_task_id = tasks[0]["task_id"] if tasks else ""
    view_token = tasks[0]["view_token"] if tasks else ""

    return {
        "status": "accepted",
        "task_id": main_task_id,
        "view_token": view_token,
        "tasks": tasks
    }


async def trigger_github_worker(
    task_id: str, repo_url: str, commit_sha: str = None, worker_attempt_id: str = None, dynamic_backend_url: str = None
):
    # Dispatch webhook to GitHub Actions worker repository
    github_token = os.getenv("GITHUB_TOKEN", "")
    worker_repo = os.getenv("WORKER_REPO", "udarshcodes/codesentinel")

    # Strip URL prefixes if WORKER_REPO is misconfigured
    if "github.com/" in worker_repo:
        worker_repo = worker_repo.split("github.com/")[-1].strip("/")

    env_backend = os.getenv("BACKEND_URL")
    # If the environment variable is hardcoded to the internal unresolvable name, ignore it
    if env_backend == "http://codesentinel-api":
        env_backend = None

    if dynamic_backend_url:
        backend_url = dynamic_backend_url
    else:
        # Fallback for local or production background loop
        fallback = "https://codesentinel-api.kindhill-aee3896c.southeastasia.azurecontainerapps.io" if os.getenv("ENVIRONMENT") == "production" else "http://codesentinel-api"
        backend_url = env_backend or fallback

    if not github_token:
        print("Warning: No GITHUB_TOKEN set. Cannot trigger worker action.")
        raise ValueError("No GITHUB_TOKEN configured on backend.")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token}",
    }

    try:
        async with httpx.AsyncClient() as client:
            if not commit_sha:
                try:
                    api_repo_url = repo_url.replace("https://github.com/", "https://api.github.com/repos/")
                    res = await client.get(f"{api_repo_url}/commits/HEAD", headers=headers)
                    if res.status_code == 200:
                        commit_sha = res.json().get("sha")
                        if commit_sha:
                            from api.job_manager import JobManager
                            from api.db import get_connection
                            def _update_commit():
                                conn = get_connection()
                                cur = conn.cursor()
                                cur.execute("UPDATE jobs SET commit_sha = ? WHERE task_id = ?", (commit_sha, task_id))
                                conn.commit()
                                conn.close()
                            await asyncio.to_thread(_update_commit)
                except Exception as e:
                    print(f"Warning: Could not fetch HEAD commit for {repo_url}: {e}")

            inputs = {"task_id": task_id, "repo_url": repo_url, "backend_url": backend_url}
            if commit_sha:
                inputs["commit_sha"] = commit_sha
            if worker_attempt_id:
                inputs["worker_attempt_id"] = worker_attempt_id

            res = await client.post(
                f"https://api.github.com/repos/{worker_repo}/actions/workflows/worker.yml/dispatches",
                headers=headers,
                json={"ref": "main", "inputs": inputs},
                timeout=10.0,
            )
            if res.status_code >= 400:
                print(f"[WorkerDispatch] Failed dispatch. Task: {task_id}, Attempt: {worker_attempt_id}, Repo: {worker_repo}, Status: {res.status_code}")
                raise RuntimeError(f"Failed to trigger worker action: {res.text}")
            else:
                print(f"[WorkerDispatch] Successful dispatch. Task: {task_id}, Attempt: {worker_attempt_id}, Repo: {worker_repo}, Workflow: worker.yml, Status: {res.status_code}")
    except Exception as e:
        print(f"[WorkerDispatch] Exception during dispatch for Task {task_id}: {str(e)}")
        # Fail the job so it doesn't get stuck in DISPATCHING silently
        from api.job_manager import JobManager
        from api.db import get_connection
        from datetime import datetime, timezone
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.transaction()
            success, seq = JobManager.transition_job_state(
                cursor, task_id, "FAILED", 
                extra_updates={"last_dispatch_error": str(e)}, 
                timestamp=now, event_name="dispatch_failed"
            )
            conn.commit()
            if success:
                JobManager._broadcast_event(task_id, "dispatch_failed", {"error": str(e)}, "FAILED", seq, now)
        except Exception as inner_e:
            conn.rollback()
            print(f"[WorkerDispatch] Failed to update job status to FAILED: {inner_e}")
        finally:
            conn.close()
        raise e


class PipelineRecoveryState(BaseModel):
    model_config = {"extra": "allow"}
    status: Optional[str] = None
    last_completed_node: Optional[str] = None
    current_node: Optional[str] = None
    retry_count: Optional[int] = None
    next_retry: Optional[str] = None
    approval_state: Optional[str] = None
    llm_waiting_state: Optional[bool] = None
    validation_state: Optional[str] = None
    security_state: Optional[str] = None
    pr_state: Optional[str] = None
    last_llm_model: Optional[str] = None
    last_llm_error: Optional[str] = None
    last_llm_exhaustion_at: Optional[str] = None

class WorkerStateResponse(BaseModel):
    task_id: str
    status: str
    repo_url: str
    commit_sha: Optional[str] = None
    pipeline_state: Optional[PipelineRecoveryState] = None
    approval_decision: Optional[str] = None
    last_completed_node: Optional[str] = None
    retry_count: Optional[int] = None
    next_retry: Optional[str] = None
    last_llm_model: Optional[str] = None
    last_llm_error: Optional[str] = None
    last_llm_exhaustion_at: Optional[str] = None
    approval_state: Optional[str] = None
    llm_waiting_state: Optional[bool] = None
    validation_state: Optional[str] = None
    security_state: Optional[str] = None
    pr_state: Optional[str] = None

class WorkerStateRequest(BaseModel):
    status: str
    pipeline_state: dict

from typing import Literal
class ApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    approval_token: str
    fix_id: str
    approval_cycle_id: str

class ApprovalTokenResponse(BaseModel):
    approval_token: str
    expires_at: str

from pydantic import Field

class LLMExhaustionRequest(BaseModel):
    pipeline_state: dict
    retry_count: int = Field(ge=0)
    next_retry: str
    model: str
    error: str = Field(min_length=1)
    reset_time: Optional[float] = None


class WorkerEvent(BaseModel):
    sequence: Optional[int] = None
    status: str
    event: str
    data: dict
    timestamp: str

@router.post("/v1/job/{task_id}/event")
@router.post("/job/{task_id}/event")  # Backward compatibility
async def worker_event_webhook(request: Request, task_id: str, event: WorkerEvent):
    """Called by the GitHub Action worker to stream granular state updates."""
    from api.worker_auth import validate_worker_attempt
    job = await validate_worker_attempt(request, task_id)

    try:
        success, sequence = JobManager.add_worker_event(
            task_id=task_id,
            status=event.status,
            event_name=event.event,
            data=event.data,
            timestamp=event.timestamp,
            sequence=None, # Ensure backend authority over event sequencing
            worker_attempt_id=job.get("worker_attempt_id"),
        )
    except ValueError as e:
        from fastapi import HTTPException
        if "Invalid state transition" in str(e):
            raise HTTPException(409, str(e))
        raise HTTPException(400, str(e))
    # Persist validated patches to ChromaDB upon pipeline completion
    if event.event == "pipeline_complete" and event.status == JobManager.COMPLETED:
        from tools import vector_store

        validated_fixes = event.data.get("validated_fixes", [])
        
        # RAG Authenticity: Scope to specific repo to prevent cross-tenant data leaks
        job = JobManager.get_job(task_id)
        repo_url = job.get("repo_url", "") if job else ""
        
        for fix in validated_fixes:
            vector_store.store_validated_fix(
                repo_url, fix["issue"], fix["patch"], fix["confidence"]
            )

    if success:
        return {"status": "ok"}
    else:
        return {"status": "ignored_duplicate"}

@router.post("/v1/job/{task_id}/state")
@router.post("/job/{task_id}/state")
async def worker_state_webhook(request: Request, task_id: str, body: WorkerStateRequest):
    """Called by the GitHub Action worker to persist LangGraph state."""
    from api.worker_auth import validate_worker_attempt
    job = await validate_worker_attempt(request, task_id)

    try:
        success = JobManager.save_worker_state(
            task_id=task_id, 
            worker_attempt_id=job.get("worker_attempt_id"), 
            status=body.status, 
            pipeline_state=body.pipeline_state
        )
        if not success:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="Stale worker attempt during state persistence")
    except ValueError as e:
        message = str(e)
        from fastapi import HTTPException
        if "human approval is pending" in message or "Stale worker attempt" in message:
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=400, detail=message)
    return {"status": "ok"}

@router.post("/v1/job/{task_id}/llm-exhaustion")
@router.post("/job/{task_id}/llm-exhaustion")
async def worker_llm_exhaustion_webhook(request: Request, task_id: str, body: LLMExhaustionRequest):
    """Called by the GitHub Action worker on LLM capacity exhaustion."""
    from api.worker_auth import validate_worker_attempt
    job = await validate_worker_attempt(request, task_id)

    def normalize_reset_time(val) -> float:
        try:
            val = float(val)
        except (ValueError, TypeError):
            return 300.0
        import math
        if math.isnan(val) or math.isinf(val) or val < 0:
            return 300.0
        if val > 86400: # cap at 1 day
            return 86400.0
        return val
        
    reset_time = normalize_reset_time(body.reset_time if body.reset_time is not None else 300.0)
    
    import datetime as dt
    now = datetime.now(timezone.utc)
    next_retry = (now + dt.timedelta(seconds=reset_time)).isoformat()
    
    # Synchronize pipeline_state with authoritative metadata to prevent DB split-brain
    body.pipeline_state["next_retry"] = next_retry
    body.pipeline_state["retry_count"] = body.retry_count
    body.pipeline_state["status"] = "WAITING_FOR_LLM_CAPACITY"
    body.pipeline_state["llm_waiting_state"] = True
    
    # 4. Set status WAITING_FOR_LLM_CAPACITY with worker attempt fencing
    success = JobManager.set_worker_waiting_capacity(task_id, worker_attempt_id=job.get("worker_attempt_id"), next_retry_timestamp=next_retry, pipeline_state=body.pipeline_state)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Stale worker attempt during LLM exhaustion persistence")
    return {"status": "ok"}

@router.get("/v1/job/{task_id}/state", response_model=WorkerStateResponse)
@router.get("/job/{task_id}/state", response_model=WorkerStateResponse)
async def worker_get_state(request: Request, task_id: str):
    """Called by the GitHub Action worker to resume LangGraph state."""
    from api.worker_auth import validate_worker_attempt
    job = await validate_worker_attempt(request, task_id)

    ps = job.get("pipeline_state") or {}
    status = job.get("status", "QUEUED")
    
    print(f"[Diag] worker_get_state: task_id={task_id}, status={status}, pipeline_state_empty={not bool(ps)}, pipeline_state_keys={list(ps.keys())}, last_completed_node={ps.get('last_completed_node')}")
    
    return WorkerStateResponse(
        task_id=task_id,
        status=status,
        repo_url=job.get("repo_url", ""),
        commit_sha=job.get("commit_sha"),
        pipeline_state=ps,
        approval_decision=job.get("approval_decision"),
        last_completed_node=ps.get("last_completed_node"),
        retry_count=ps.get("retry_count"),
        next_retry=job.get("next_retry"),
        last_llm_model=ps.get("last_llm_model"),
        last_llm_error=ps.get("last_llm_error"),
        last_llm_exhaustion_at=ps.get("last_llm_exhaustion_at"),
        approval_state=job.get("approval_decision"),
        llm_waiting_state=ps.get("llm_waiting_state"),
        validation_state=ps.get("validation_state"),
        security_state=ps.get("security_state"),
        pr_state=ps.get("pr_state")
    )

def _validate_view_token(request: Request, job: dict):
    """
    Validates the view_token capability.
    
    Security Design: View Token Minting Capability (Design B)
    The View Token is intentionally allowed to mint a narrowly scoped ephemeral approval capability.
    This capability is strictly bound by:
    - Task identity (task_id)
    - Current workflow cycle identity (approval_cycle_id)
    - Current repair fix identity (fix_id)
    - Short ephemeral lifetime (15 minutes)
    
    It CANNOT mutate workflow state, approve fixes, or access cross-task data.
    """
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(401, "Missing view_token")

    hashed_token = hashlib.sha256(token.encode()).hexdigest()
    if not job.get("view_token") or not hmac.compare_digest(job["view_token"], hashed_token):
        raise HTTPException(401, "Invalid view_token")

@router.get("/v1/job/{task_id}/stream-capability")
@router.get("/job/{task_id}/stream-capability")
async def get_stream_capability(request: Request, task_id: str):
    """Provides a single-use, short-lived SSE capability for authorized viewers."""
    job = JobManager.get_job(task_id)
    if not job:
        raise HTTPException(404, "Job not found")

    _validate_view_token(request, job)

    capability = JobManager.create_sse_capability(task_id)
    return {"capability": capability}

@router.get("/v1/job/{task_id}/view")
@router.get("/job/{task_id}/view")
async def frontend_view_state(request: Request, task_id: str):
    """Called by the frontend to view job state securely using a view_token."""
    job = JobManager.get_job(task_id)
    if not job:
        raise HTTPException(404, "Job not found")

    _validate_view_token(request, job)

    # Scrub credential material using public serializer
    job = JobManager.to_public_dict(job)
    
    # Return last sequence for SSE hydration
    job["last_sequence"] = JobManager.get_latest_sequence(task_id)

    # Hydrate agents from event history
    events = JobManager.get_events(task_id)
    agents = []
    for evt in events:
        if evt.get("event") == "agent_complete":
            data = evt.get("data", {})
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse agent_complete data: {e}")
                    data = {}
            if data and "agent" in data:
                agents.append(data)
    job["agents"] = agents

    return job

class RecoverCredentialRequest(BaseModel):
    approval_cycle_id: str
    fix_id: str

@router.post("/v1/job/{task_id}/issue-approval-token")
@router.post("/job/{task_id}/issue-approval-token", response_model=IssueApprovalTokenResponse)
@limiter.limit("10/minute")
async def issue_approval_token(request: Request, task_id: str):
    """Securely issue a new raw approval token for the current pending approval cycle."""
    job = JobManager.get_job(task_id)
    if not job:
        raise HTTPException(404, "Job not found")

    _validate_view_token(request, job)

    import sqlite3
    import json
    from api.db import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        conn.transaction()
        
        try:
            p_state_str, worker_attempt_id, active_row = JobManager.validate_approval_context(cursor, task_id, None, None, None, False)
        except ValueError as e:
            raise HTTPException(400, str(e))
            
        p_state = json.loads(p_state_str)
        approval_cycle_id = p_state.get("approval_cycle_id")
        fix = p_state.get("approval_payload")
        
        if active_row:
            credential_id, cred_worker_id, _, expires_at = active_row
            conn.commit()
            conn.close()
            return IssueApprovalTokenResponse(
                status="active",
                task_id=task_id,
                approval_cycle_id=approval_cycle_id,
                fix_id=fix.get("fix_id"),
                expires_at=expires_at,
                approval_token=None
            )
            
        import secrets, hashlib, uuid
        from datetime import timedelta
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(minutes=15)).isoformat()
        
        credential_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, worker_attempt_id) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            (credential_id, task_id, fix.get("fix_id"), approval_cycle_id, token_hash, expires, now.isoformat(), worker_attempt_id)
        )
        
        conn.commit()
    except HTTPException:
        conn.rollback()
        conn.close()
        raise
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(500, f"Internal error during token issuance: {str(e)}")
        
    conn.close()
    return IssueApprovalTokenResponse(
        status="issued",
        task_id=task_id,
        approval_cycle_id=approval_cycle_id,
        fix_id=fix.get("fix_id"),
        expires_at=expires,
        approval_token=raw_token
    )

@router.post("/v1/job/{task_id}/recover-credential", response_model=RecoverCredentialResponse)
@router.post("/job/{task_id}/recover-credential", response_model=RecoverCredentialResponse)
@limiter.limit("3/minute")
async def recover_credential(request: Request, task_id: str, body: RecoverCredentialRequest):
    """Explicitly recover an approval credential. Revokes the old one and issues a new one. Tightly bound capability."""
    job = JobManager.get_job(task_id)
    if not job:
        raise HTTPException(404, "Job not found")

    _validate_view_token(request, job)

    import sqlite3
    import uuid
    from api.db import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        conn.transaction()
        
        # 1. Validate everything inside transaction
        try:
            p_state_str, current_worker_attempt_id, active_cred_row = JobManager.validate_approval_context(
                cursor, task_id, body.approval_cycle_id, body.fix_id, None, False
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
            
        import secrets
        import hashlib
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(minutes=15)).isoformat()
        
        # Revoke existing if any
        if active_cred_row:
            credential_id, cred_worker_attempt_id, _, _ = active_cred_row
            
            if current_worker_attempt_id and cred_worker_attempt_id and current_worker_attempt_id != cred_worker_attempt_id:
                raise HTTPException(400, "Stale worker attempt detected during recovery.")
                
            cursor.execute(
                "UPDATE approval_credentials SET status = 'revoked', revoked_at = ? WHERE credential_id = ?",
                (now.isoformat(), credential_id)
            )
            
        import json
        p_state = json.loads(p_state_str) if p_state_str else {}
        approval_cycle_id = p_state.get("approval_cycle_id")
        fix = p_state.get("approval_payload") or {}
        fix_id = fix.get("fix_id") or body.fix_id
        
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            
        credential_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO approval_credentials (credential_id, task_id, fix_id, approval_cycle_id, token_hash, status, expires_at, created_at, worker_attempt_id) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            (credential_id, task_id, fix_id, approval_cycle_id, token_hash, expires, now.isoformat(), current_worker_attempt_id)
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        conn.close()
        raise
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(500, f"Internal error during token recovery: {str(e)}")
    conn.close()
    return RecoverCredentialResponse(
        status="recovered",
        task_id=task_id,
        approval_cycle_id=approval_cycle_id,
        fix_id=fix_id,
        expires_at=expires,
        approval_token=raw_token
    )

@router.post("/v1/job/{task_id}/heartbeat")
@router.post("/job/{task_id}/heartbeat")
async def worker_heartbeat(request: Request, task_id: str):
    """Called periodically by the worker to maintain its lease."""
    from api.worker_auth import validate_worker_attempt
    # Validate worker attempt BEFORE opening a DB connection
    job = await validate_worker_attempt(request, task_id)

    from api.job_manager import get_connection
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute(
            "UPDATE jobs SET worker_heartbeat_at = ?, updated_at = ? WHERE task_id = ? AND worker_attempt_id = ?",
            (now, now, task_id, job.get("worker_attempt_id"))
        )
        if cursor.rowcount == 0:
            raise HTTPException(409, "Stale worker attempt detected during heartbeat")
        conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        print(f"CRITICAL: Heartbeat database failure for {task_id}: {type(e).__name__}")
        # Log generic error to client, preserving security
        raise HTTPException(status_code=500, detail="Backend infrastructure error during heartbeat")
    finally:
        if conn:
            conn.close()

    return {"status": "ok"}

from pydantic import BaseModel

@router.post("/v1/approve/{task_id}")
@router.post("/approve/{task_id}")
async def submit_approval(request: Request, task_id: str, body: ApprovalRequest):
    """
    Unblocks the pipeline that is paused at awaiting_approval.
    """
    import hashlib
    from api.job_manager import JobManager
    
    if not body.fix_id:
        raise HTTPException(400, "Missing fix_id")

    hashed_token = hashlib.sha256(body.approval_token.encode()).hexdigest()
    
    try:
        res = JobManager.resolve_approval(task_id, body.decision, hashed_token, body.fix_id, body.approval_cycle_id)
        return res
    except ValueError as e:
        err_str = str(e)
        if "Invalid approval_token" in err_str:
            raise HTTPException(401, detail={"error": "authentication", "message": err_str})
        elif "expired" in err_str:
            raise HTTPException(400, detail={"error": "expired_approval", "message": err_str})
        elif "No pipeline awaiting approval" in err_str or "Task is not in a state that can be approved" in err_str or "Job not found" in err_str:
            raise HTTPException(404, detail={"error": "task_not_found", "message": err_str})
        elif "Approval already resolved" in err_str:
            raise HTTPException(400, detail={"error": "already_resolved", "message": err_str})
        else:
            raise HTTPException(400, detail={"error": "invalid_approval", "message": err_str})
    except Exception as e:
        raise HTTPException(500, detail={"error": "backend_failure", "message": str(e)})


@router.post("/v1/webhook/github")
@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle GitHub webhook events for CI/CD integration.
    Automatically triggers analysis on push to main or pull_request opened/synchronized.
    Verifies the X-Hub-Signature-256 header if GITHUB_WEBHOOK_SECRET is configured.
    """
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    
    if os.getenv("ENVIRONMENT") == "production" and not webhook_secret:
        raise HTTPException(
            status_code=403, detail="Webhook secret missing in production"
        )
        
    if webhook_secret:
        signature_header = request.headers.get("X-Hub-Signature-256", "")
        if not signature_header:
            raise HTTPException(
                status_code=403, detail="Missing X-Hub-Signature-256 header"
            )

        body_bytes = await request.body()
        expected_sig = (
            "sha256="
            + hmac.HMAC(webhook_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        )

        if not hmac.compare_digest(expected_sig, signature_header):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    event_type = request.headers.get("X-GitHub-Event")
    if not event_type:
        return {"status": "ignored", "reason": "No X-GitHub-Event header"}

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse webhook JSON payload: {e}")
        return {"status": "error", "reason": "Invalid JSON"}

    repo_url = payload.get("repository", {}).get("html_url")
    if not repo_url:
        return {"status": "ignored", "reason": "No repository URL in payload"}

    should_analyze = False
    commit_sha = None

    if event_type == "push":
        ref = payload.get("ref", "")
        if ref in ["refs/heads/main", "refs/heads/master"]:
            should_analyze = True
            commit_sha = payload.get("after")
    elif event_type == "pull_request":
        action = payload.get("action")
        if action in ["opened", "synchronize"]:
            should_analyze = True
            commit_sha = payload.get("pull_request", {}).get("head", {}).get("sha")

    if should_analyze:
        import secrets
        task_id = str(uuid.uuid4())
        view_token = secrets.token_urlsafe(32)
        JobManager.create_job(task_id, repo_url, view_token=view_token, commit_sha=commit_sha)
        
        worker_attempt_id = JobManager.claim_waiting_job(task_id)
        if worker_attempt_id:
            base_url = str(request.base_url).rstrip("/")
            if request.headers.get("x-forwarded-proto") == "https" and base_url.startswith("http://"):
                base_url = base_url.replace("http://", "https://", 1)
            background_tasks.add_task(trigger_github_worker, task_id, repo_url, commit_sha, worker_attempt_id, base_url)
        return {"status": "accepted", "task_id": task_id, "repo_url": repo_url}

    return {"status": "ignored", "reason": f"Event {event_type} ignored"}

@router.post("/v1/job/{task_id}/retry-pr")
@router.post("/job/{task_id}/retry-pr")
@limiter.limit("5/minute")
async def retry_pr_creation(request: Request, task_id: str, background_tasks: BackgroundTasks):
    job = JobManager.get_job(task_id)
    if not job:
        raise HTTPException(404, "Job not found")

    _validate_view_token(request, job)

    if job["status"] not in ["FAILED", "COMPLETED", "NEEDS_REVIEW"]:
        raise HTTPException(400, "Job must be in a terminal state to retry PR creation")

    import json
    from api.db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    try:
        conn.transaction()
        cursor.execute(getattr(cursor, 'for_update', lambda q: q)("SELECT pipeline_state FROM jobs WHERE task_id = ?"), (task_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
            
        p_state = json.loads(row[0] or "{}")
        p_state["pr_error"] = None
        p_state["pr_url"] = None
        p_state["pr_state"] = None
        p_state["last_completed_node"] = "security_verifier"
        
        cursor.execute(
            "UPDATE jobs SET pipeline_state = ?, status = 'QUEUED' WHERE task_id = ?",
            (json.dumps(p_state), task_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        conn.close()

    worker_attempt_id = await asyncio.to_thread(JobManager.claim_waiting_job, task_id)
    if not worker_attempt_id:
        raise HTTPException(500, "Failed to claim job for retry")

    base_url = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https" and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://", 1)

    background_tasks.add_task(
        trigger_github_worker, task_id, job["repo_url"], job.get("commit_sha"), worker_attempt_id, base_url
    )

    return {"status": "accepted"}

# Admin Telemetry API
from tools.key_dispatcher import get_usage_report

class LoginRequest(BaseModel):
    secret: str

@router.post("/v1/admin/login")
@limiter.limit("5/minute")
async def admin_login(request: Request, body: LoginRequest, response: Response):
    admin_secret = os.getenv("ADMIN_SECRET", "")
    # Use hmac.compare_digest for constant-time comparison
    if not admin_secret or not hmac.compare_digest(body.secret.encode('utf-8'), admin_secret.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Create DB-backed session
    session_id = JobManager.create_admin_session()
    
    # Issue HTTP-Only cookie for auth
    is_prod = os.getenv("ENVIRONMENT") == "production"
    response.set_cookie(
        key="admin_session",
        value=session_id,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=3600
    )
    return {"status": "ok"}

@router.post("/v1/admin/logout")
async def admin_logout(request: Request, response: Response):
    session_id = request.cookies.get("admin_session")
    if session_id:
        JobManager.delete_admin_session(session_id)
    is_prod = os.getenv("ENVIRONMENT") == "production"
    response.delete_cookie(key="admin_session", httponly=True, secure=is_prod, samesite="lax")
    return {"status": "ok"}

@router.get("/v1/admin/telemetry")
@limiter.limit("10/minute")
async def admin_telemetry(request: Request, admin_session: str = Cookie(None)):
    if not JobManager.validate_admin_session(admin_session):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    from tools.llm_router import get_telemetry as get_agent_telemetry
    from tools.response_cache import cache_metrics
    
    usage = get_usage_report()
    agents = get_agent_telemetry()
    pipeline = JobManager.get_pipeline_health_metrics()
    
    failed_jobs = pipeline.get("failed", 0) + pipeline.get("active_failed", 0)
    
    return {
        "status": "ok",
        "pipeline_health": "stable" if failed_jobs == 0 else "unstable",
        "overview": {
            "total_models": len(agents),
            "total_keys": usage.get("overview", {}).get("active_primary_keys", 0),
            "status": "EMERGENCY" if usage.get("overview", {}).get("emergency_engaged") else "ACTIVE",
            "cache_metrics": cache_metrics.get("global", {"hits": 0, "misses": 0})
        },
        "models": {
            agent: {
                "requests": data.get("calls", 0),
                "tokens": data.get("prompt_tokens", 0) + data.get("completion_tokens", 0),
                "failures": 0,
                "rate_limit_status": "ok"
            } for agent, data in agents.items()
        },
        "credentials": {
            f"key_{k}": {
                "all_models": {
                    "status": v.get("status", "active"),
                    "tokens": v.get("tokens_used", 0),
                    "failures": 0
                }
            } for k, v in usage.get("primary_keys", {}).items()
        }
    }
