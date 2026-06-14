from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class AnalyzeRequest(BaseModel):
    repo_url: str

import os
import httpx

@router.post("/analyze")
async def start_analysis(request: AnalyzeRequest):
    repo_url = request.repo_url
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

    return {"status": "accepted", "repo_urls": repos_to_analyze}

from fastapi import HTTPException
from orchestrator import approval_events, broadcast_sse

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
    
    # Broadcast that the pipeline is resuming
    await broadcast_sse(task_id, {
        "event": "approval_resolved", 
        "decision": decision
    })
    
    return {'status': 'ok', 'decision': decision}