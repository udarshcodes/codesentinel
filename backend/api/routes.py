from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
import os
import re
import hmac
import hashlib
import httpx
import uuid
from datetime import datetime
from state import approval_events
from limiter import limiter
from api.job_manager import JobManager

router = APIRouter()


class AnalyzeRequest(BaseModel):
    repo_url: str
    commit_sha: str = None


@router.post("/v1/analyze")
@router.post("/analyze")  # Backward compatibility
@limiter.limit("2/minute")
async def start_analysis(request: Request, body: AnalyzeRequest, background_tasks: BackgroundTasks):
    repo_url = body.repo_url.strip()
    if repo_url.startswith("github.com/"):
        repo_url = "https://" + repo_url
        body.repo_url = repo_url

    # Validate repo_url format
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
        # Generate a stable UUID based on repo name for easy frontend connection
        # Or just a pure UUID. Let's use pure UUID so we can have multiple runs.
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)

        # 1. Create Job in Database
        JobManager.create_job(task_id, r_url)

        # 2. Trigger GitHub Action (Workflow Dispatch)
        # We fire and forget this async call so we don't block the API
        background_tasks.add_task(
            trigger_github_worker, task_id, r_url, body.commit_sha
        )

    # If it was a single repo, return just that task_id for backward compatibility
    # But also include the array of task_ids for Multi-Repo mode
    main_task_id = task_ids[0] if task_ids else ""

    return {
        "status": "accepted",
        "task_id": main_task_id,
        "task_ids": task_ids,
        "repo_urls": repos_to_analyze,
    }


async def trigger_github_worker(task_id: str, repo_url: str, commit_sha: str = None):
    # This triggers the worker.yml in the CodeSentinel repo.
    # It assumes the action is stored in the same repo we are running from,
    # or a central worker repo defined by WORKER_REPO_URL.
    github_token = os.getenv("GITHUB_TOKEN", "")
    worker_repo = os.getenv("WORKER_REPO", "udarshcodes/codesentinel")
    
    # Robustly handle if the user accidentally put the full URL in WORKER_REPO
    if "github.com/" in worker_repo:
        worker_repo = worker_repo.split("github.com/")[-1].strip("/")

    backend_url = os.getenv("BACKEND_URL", "http://codesentinel-api") # Fallback for local
    
    if not github_token:
        print("Warning: No GITHUB_TOKEN set. Cannot trigger worker action.")
        JobManager.add_event(task_id, 0, JobManager.FAILED, "error", {"error": "No GITHUB_TOKEN configured on backend."}, datetime.utcnow().isoformat())
        return

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token}",
    }
    
    inputs = {
        "task_id": task_id,
        "repo_url": repo_url,
        "backend_url": backend_url
    }
    if commit_sha:
        inputs["commit_sha"] = commit_sha

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"https://api.github.com/repos/{worker_repo}/actions/workflows/worker.yml/dispatches",
                headers=headers,
                json={"ref": "main", "inputs": inputs},
                timeout=10.0
            )
            if res.status_code >= 400:
                print(f"Error triggering worker: {res.status_code} - {res.text}")
                JobManager.add_event(task_id, -1, JobManager.FAILED, "error", {"error": f"Failed to trigger worker action: {res.text}"}, datetime.utcnow().isoformat())
        except Exception as e:
            print(f"Exception triggering worker: {e}")
            JobManager.add_event(task_id, -1, JobManager.FAILED, "error", {"error": f"Failed to trigger worker action: {e}"}, datetime.utcnow().isoformat())


# --- WORKER WEBHOOK ENDPOINTS ---

class WorkerEvent(BaseModel):
    sequence: int
    status: str
    event: str
    data: dict
    timestamp: str

@router.post("/v1/job/{task_id}/event")
@router.post("/job/{task_id}/event")  # Backward compatibility
async def worker_event_webhook(task_id: str, event: WorkerEvent):
    """Called by the GitHub Action worker to stream granular state updates."""
    success = JobManager.add_event(
        task_id, event.sequence, event.status, event.event, event.data, event.timestamp
    )
    # If the event was a final complete event, we also need to persist patches to ChromaDB.
    # The worker packages patches into the data object of pipeline_complete.
    if event.event == "pipeline_complete" and event.status == JobManager.COMPLETED:
        from tools import vector_store
        # The worker should pass validated_fixes in the data payload
        validated_fixes = event.data.get("validated_fixes", [])
        for fix in validated_fixes:
            vector_store.store_validated_fix(fix["issue"], fix["patch"], fix["confidence"])
            
    if success:
        return {"status": "ok"}
    else:
        return {"status": "ignored_duplicate"}


@router.post("/v1/approve/{task_id}")
@router.post("/approve/{task_id}")
async def submit_approval(task_id: str, body: dict):
    """
    Body: {decision: 'approved' | 'rejected'}
    Unblocks the pipeline that is paused at awaiting_approval.
    """
    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved or rejected")

    event_dict = approval_events.get(task_id)
    if not event_dict:
        raise HTTPException(404, "No pipeline awaiting approval for this task")

    event_dict["decision"] = decision
    event_dict["event"].set()  # Unblock the waiting coroutine

    # Broadcast that the pipeline is resuming via the sse queue
    # We use a helper function from orchestrator to just put it in the queue
    from state import sse_queues

    if task_id in sse_queues:
        await sse_queues[task_id].put(
            {"event": "approval_resolved", "data": {"decision": decision}}
        )

    return {"status": "ok", "decision": decision}


@router.post("/v1/webhook/github")
@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle GitHub webhook events for CI/CD integration.
    Automatically triggers analysis on push to main or pull_request opened/synchronized.
    Verifies the X-Hub-Signature-256 header if GITHUB_WEBHOOK_SECRET is configured.
    """
    # Verify webhook signature if a secret is configured
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
        # Trigger on push to main or master
        if ref in ["refs/heads/main", "refs/heads/master"]:
            should_analyze = True
            commit_sha = payload.get("after")
    elif event_type == "pull_request":
        action = payload.get("action")
        # Trigger on PR opened or updated
        if action in ["opened", "synchronize"]:
            should_analyze = True
            commit_sha = payload.get("pull_request", {}).get("head", {}).get("sha")

    if should_analyze:
        task_id = str(uuid.uuid4())
        background_tasks.add_task(trigger_github_worker, task_id, repo_url, commit_sha)
        return {"status": "accepted", "task_id": task_id, "repo_url": repo_url}

    return {"status": "ignored", "reason": f"Event {event_type} ignored"}
