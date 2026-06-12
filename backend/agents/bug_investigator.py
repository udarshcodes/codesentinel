import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from models.pipeline_state import PipelineState
from config import GEMINI_API_KEY
from tools.vector_store import query_past_fixes

async def agent_bug_investigator(state: PipelineState):
    repo_local_path = state.get("repo_local_path", "")
    static_findings = state.get("static_findings", [])
    dependency_findings = state.get("dependency_findings", [])
    knowledge_graph = state.get("knowledge_graph", {})
    
    all_findings = static_findings + dependency_findings
    investigated_issues = []
    
    if not all_findings or not GEMINI_API_KEY:
        return {"investigated_issues": investigated_issues}
        
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=GEMINI_API_KEY)
    
    for idx, finding in enumerate(all_findings):
        issue_desc = finding.get("issue", str(finding))
        file_path = finding.get("file", "")
        
        file_content = ""
