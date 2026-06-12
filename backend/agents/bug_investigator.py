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
    
