from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import os
import re
import httpx
import uuid
from api.sse import run_pipeline_worker
from state import approval_events

router = APIRouter()

class AnalyzeRequest(BaseModel):
    repo_url: str
    commit_sha: str = None

@router.post("/v1/analyze")
@router.post("/analyze") # Backward compatibility
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    repo_url = request.repo_url

    # Validate repo_url format
    if not repo_url.endswith("/*"):
        if not re.match(r'^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:\.git)?$', repo_url):
            raise HTTPException(400, "Invalid repository URL. Only GitHub HTTPS URLs are accepted (e.g., https://github.com/owner/repo).")

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
                res = await client.get(f"https://api.github.com/users/{org_name}/repos?type=owner&sort=updated&per_page=5", headers=headers)
                if res.status_code == 200:
                    repos = res.json()
                    repos_to_analyze = [r["html_url"] for r in repos if not r["archived"]]
        except Exception as e:
            print(f"Error fetching org repos: {e}")

    task_ids = []
    for r_url in repos_to_analyze:
        # Generate a stable UUID based on repo name for easy frontend connection
        # Or just a pure UUID. Let's use pure UUID so we can have multiple runs.
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        
        # Fire and forget the background task
        background_tasks.add_task(run_pipeline_worker, task_id, r_url, request.commit_sha)

    # If it was a single repo, return just that task_id for backward compatibility
    # But also include the array of task_ids for Multi-Repo mode
    main_task_id = task_ids[0] if task_ids else ""

    return {
        "status": "accepted",
        "task_id": main_task_id,
        "task_ids": task_ids,
        "repo_urls": repos_to_analyze
    }

@router.post("/v1/approve/{task_id}")
@router.post("/approve/{task_id}")
async def submit_approval(task_id: str, body: dict):
    '''
    Body: {decision: 'approved' | 'rejected'}
    Unblocks the pipeline that is paused at awaiting_approval.
    '''
    decision = body.get('decision')
    if decision not in ('approved', 'rejected'):
        raise HTTPException(400, 'decision must be approved or rejected')
        
    event_dict = approval_events.get(task_id)
    if not event_dict:
        raise HTTPException(404, 'No pipeline awaiting approval for this task')
        
    event_dict['decision'] = decision
    event_dict['event'].set() # Unblock the waiting coroutine
    
    # Broadcast that the pipeline is resuming via the sse queue
    # We use a helper function from orchestrator to just put it in the queue
    from state import sse_queues
    if task_id in sse_queues:
        await sse_queues[task_id].put({
            "event": "approval_resolved", 
            "data": {"decision": decision}
        })
    
    return {'status': 'ok', 'decision': decision}