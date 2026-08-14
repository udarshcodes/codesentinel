from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
import os
import re
import hmac
import hashlib
import httpx
import uuid
from datetime import datetime, timezone
from state import approval_events
from limiter import limiter
from api.job_manager import JobManager

router = APIRouter()


class AnalyzeRequest(BaseModel):
    repo_url: str
    commit_sha: str = None


@router.post("/v1/analyze")
@router.post("/analyze")
@limiter.limit("2/minute")
async def start_analysis(
    request: Request, body: AnalyzeRequest, background_tasks: BackgroundTasks
):
    base_url = str(request.base_url).rstrip("/")
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
                res = await client.get(
                    f"https://api.github.com/orgs/{org_name}/repos?sort=updated&per_page=10",
                    headers=headers,
                )
                if res.status_code != 200:
                    res = await client.get(
                        f"https://api.github.com/users/{org_name}/repos?type=owner&sort=updated&per_page=10",
                        headers=headers,
                    )
                if res.status_code == 200:
                    repos = res.json()
                    fetched_repos = [
                        r["html_url"] for r in repos if not r.get("archived")
                    ]
        except Exception as e:
            print(f"Error fetching org repos: {e}")

        if not fetched_repos:
            raise HTTPException(
                400,
                f"Could not find any active public repositories for organization/user '{org_name}'.",
            )
        repos_to_analyze = fetched_repos

    task_ids = []
    for r_url in repos_to_analyze:
        # Use UUIDs to support multiple concurrent runs
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)

        JobManager.create_job(task_id, r_url)

        # Dispatch non-blocking background task to GitHub worker
        background_tasks.add_task(
            trigger_github_worker, task_id, r_url, body.commit_sha, base_url
        )

    # Return legacy single task_id and array of multi-repo task_ids
    main_task_id = task_ids[0] if task_ids else ""

    return {
        "status": "accepted",
        "task_id": main_task_id,
        "task_ids": task_ids,
        "repo_urls": repos_to_analyze,
    }


async def trigger_github_worker(
    task_id: str, repo_url: str, commit_sha: str = None, dynamic_backend_url: str = None
):
    # Dispatch webhook to GitHub Actions worker repository
    github_token = os.getenv("GITHUB_TOKEN", "")
    worker_repo = os.getenv("WORKER_REPO", "udarshcodes/codesentinel")

    # Strip URL prefixes if WORKER_REPO is misconfigured
    if "github.com/" in worker_repo:
        worker_repo = worker_repo.split("github.com/")[-1].strip("/")

    if dynamic_backend_url:
        backend_url = os.getenv("BACKEND_URL", dynamic_backend_url)
    else:
        backend_url = os.getenv(
            "BACKEND_URL", "http://codesentinel-api"
        )  # Fallback for local

    if not github_token:
        print("Warning: No GITHUB_TOKEN set. Cannot trigger worker action.")
        JobManager.add_event(
            task_id,
            0,
            JobManager.FAILED,
            "error",
            {"error": "No GITHUB_TOKEN configured on backend."},
            datetime.utcnow().isoformat(),
        )
        return

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token}",
    }

    inputs = {"task_id": task_id, "repo_url": repo_url, "backend_url": backend_url}
    if commit_sha:
        inputs["commit_sha"] = commit_sha

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"https://api.github.com/repos/{worker_repo}/actions/workflows/worker.yml/dispatches",
                headers=headers,
                json={"ref": "main", "inputs": inputs},
                timeout=10.0,
            )
            if res.status_code >= 400:
                print(f"Error triggering worker: {res.status_code} - {res.text}")
                JobManager.add_event(
                    task_id,
                    -1,
                    JobManager.FAILED,
                    "error",
                    {"error": f"Failed to trigger worker action: {res.text}"},
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
        except Exception as e:
            print(f"Exception triggering worker: {e}")
            JobManager.add_event(
                task_id,
                -1,
                JobManager.FAILED,
                "error",
                {"error": f"Failed to trigger worker action: {e}"},
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )


class WorkerEvent(BaseModel):
    sequence: int
    status: str
    event: str
    data: dict
    timestamp: str


@router.post("/v1/job/{task_id}/event")
@router.post("/job/{task_id}/event")  # Backward compatibility
async def worker_event_webhook(request: Request, task_id: str, event: WorkerEvent):
    """Called by the GitHub Action worker to stream granular state updates."""
    # HMAC Replay Protection
    worker_secret = os.getenv("WORKER_WEBHOOK_SECRET", "")
    if worker_secret:
        signature_header = request.headers.get("X-Worker-Signature", "")
        if not signature_header:
            raise HTTPException(status_code=403, detail="Missing X-Worker-Signature header")

        body_bytes = await request.body()
        
        # Protect against replay by ensuring timestamp is fresh (within 5 minutes)
        try:
            event_time = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")).timestamp()
            now = datetime.now(timezone.utc).timestamp()
            if abs(now - event_time) > 300:
                raise HTTPException(status_code=403, detail="Expired timestamp (replay protection)")
        except ValueError:
            pass # fallback if timestamp is malformed

        # The signature includes method, path, task_id, sequence, timestamp, and body
        msg = f"{request.method}:{request.url.path}:{task_id}:{event.sequence}:{event.timestamp}:".encode() + body_bytes
        expected_sig = "sha256=" + hmac.HMAC(worker_secret.encode(), msg, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_sig, signature_header):
            raise HTTPException(status_code=403, detail="Invalid worker signature")
    success = JobManager.add_event(
        task_id, event.sequence, event.status, event.event, event.data, event.timestamp
    )
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


@router.post("/v1/approve/{task_id}")
@router.post("/approve/{task_id}")
async def submit_approval(request: Request, task_id: str, body: dict):
    """
    Body: {decision: 'approved' | 'rejected'}
    Unblocks the pipeline that is paused at awaiting_approval.
    """
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if admin_secret:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {admin_secret}":
            raise HTTPException(401, "Unauthorized")

    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved or rejected")

    event_dict = approval_events.get(task_id)
    if not event_dict:
        raise HTTPException(404, "No pipeline awaiting approval for this task")

    event_dict["decision"] = decision
    event_dict["approved_by"] = "admin" # Can be extracted from token in future
    event_dict["approved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    event_dict["event"].set()

    # Broadcast pipeline resumption via SSE
    from state import broadcast_sse
    await broadcast_sse(task_id, {"event": "approval_resolved", "data": {"decision": decision}})

    return {"status": "ok", "decision": decision}


@router.post("/v1/webhook/github")
@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle GitHub webhook events for CI/CD integration.
    Automatically triggers analysis on push to main or pull_request opened/synchronized.
    Verifies the X-Hub-Signature-256 header if GITHUB_WEBHOOK_SECRET is configured.
    """
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
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
    except Exception:
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
        task_id = str(uuid.uuid4())
        JobManager.create_job(task_id, repo_url)
        background_tasks.add_task(trigger_github_worker, task_id, repo_url, commit_sha)
        return {"status": "accepted", "task_id": task_id, "repo_url": repo_url}

    return {"status": "ignored", "reason": f"Event {event_type} ignored"}
