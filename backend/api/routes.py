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

class ApproveRequest(BaseModel):
    patch_id: int
    approved: bool

@router.post("/approve")
async def approve_fix(request: ApproveRequest):
    # Resume the LangGraph here in a real implementation
    return {"status": "resumed", "approved": request.approved}