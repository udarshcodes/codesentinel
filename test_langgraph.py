import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
import asyncio
from orchestrator import app as langgraph_app

async def main():
    state = {
        "task_id": "test",
        "repo_url": "test",
        "commit_sha": "test",
        "repo_local_path": "",
        "knowledge_graph": {},
        "dependency_findings": [],
        "static_findings": [],
        "investigated_issues": [],
        "repair_plan": [],
        "patches": [],
        "validation_results": [],
        "security_verified": False,
        "pr_url": "",
        "pr_error": "",
        "retry_count": 0,
        "awaiting_approval": False,
        "confidence_score": 0.0,
        "dependency_graph": {},
        "last_completed_node": "",
    }
    
    astream_iter = langgraph_app.astream(state)
    while True:
        try:
            output = await anext(astream_iter, None)
            if output is None:
                break
            print("Yielded:", output.keys())
        except Exception as e:
            print("Error:", e)
            break

if __name__ == "__main__":
    asyncio.run(main())
