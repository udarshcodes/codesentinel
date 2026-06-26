from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
import os
import re
import hmac
import hashlib
import httpx
import uuid
from api.sse import run_pipeline_worker
from state import approval_events

router = APIRouter()


class AnalyzeRequest(BaseModel):
    repo_url: str
    commit_sha: str = None


@router.post("/v1/analyze")
@router.post("/analyze")  # Backward compatibility
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    repo_url = request.repo_url

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

        try:
            async with httpx.AsyncClient() as client:
                # Try orgs/ endpoint first (for GitHub Organizations), fallback to users/
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
                    repos_to_analyze = [
                        r["html_url"] for r in repos if not r.get("archived")
                    ]
        except Exception as e:
            print(f"Error fetching org repos: {e}")

    task_ids = []
    for r_url in repos_to_analyze:
        # Generate a stable UUID based on repo name for easy frontend connection
        # Or just a pure UUID. Let's use pure UUID so we can have multiple runs.
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)

        # Fire and forget the background task
        background_tasks.add_task(
            run_pipeline_worker, task_id, r_url, request.commit_sha
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
            + hmac.new(webhook_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
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
        import uuid

        task_id = str(uuid.uuid4())
        background_tasks.add_task(run_pipeline_worker, task_id, repo_url, commit_sha)
        return {"status": "accepted", "task_id": task_id, "repo_url": repo_url}

    return {"status": "ignored", "reason": f"Event {event_type} ignored"}
