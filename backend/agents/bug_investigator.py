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
        if file_path and repo_local_path:
            full_path = os.path.join(repo_local_path, file_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r") as f:
                        file_content = f.read()
                except:
                    pass
                    
        # RAG - Query past fixes
        past_context = query_past_fixes(issue_desc)
        past_context_str = "\n".join(past_context) if past_context else "None"
        
