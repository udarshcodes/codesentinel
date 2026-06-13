import os
import tempfile
from git import Repo
from models.pipeline_state import PipelineState
from config import GROQ_API_KEY
from tools.llm_router import invoke_llm
from tools import context_cache

async def agent_repo_mapper(state: PipelineState):
    repo_url = state["repo_url"]
    
    # 1. Clone repository
    temp_dir = tempfile.mkdtemp(prefix="codesentinel_")
    Repo.clone_from(repo_url, temp_dir)
    
    # 2. Walk directory to find extensions and dependency files
    extensions = {}
    dep_files = []
    
    for root, dirs, files in os.walk(temp_dir):
        if ".git" in root:
            continue
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext:
                extensions[ext] = extensions.get(ext, 0) + 1
            if file in ["requirements.txt", "package.json", "pom.xml", "go.mod"]:
                rel_path = os.path.relpath(os.path.join(root, file), temp_dir)
                dep_files.append(rel_path)
                
    # 3. LLM analysis — Tier 1 (simple structural classification)
    if GROQ_API_KEY:
        prompt = f"""Analyze the following repository structure data to determine the primary language and framework.
File extensions frequency: {extensions}
Dependency files found: {dep_files}

Return ONLY valid JSON with keys: 'language', 'framework', 'modules'."""

        try:
            knowledge_graph = invoke_llm(
                prompt,
                agent_name="repo_mapper",
                tier=1,
                expect_json=True,
            )
            if not isinstance(knowledge_graph, dict) or knowledge_graph.get("error"):
                knowledge_graph = {"language": "unknown", "framework": "unknown", "modules": []}
        except Exception as e:
            print(f"[RepoMapper] LLM error: {e}")
            knowledge_graph = {"language": "unknown", "framework": "unknown", "modules": []}
    else:
        knowledge_graph = {"language": "Python (Mock - No API Key)", "framework": "FastAPI", "modules": []}
    
    # Cache the knowledge graph for downstream agents
    context_cache.store(repo_url, "knowledge_graph", knowledge_graph)
        
    return {
        "repo_local_path": temp_dir,
        "knowledge_graph": knowledge_graph
    }