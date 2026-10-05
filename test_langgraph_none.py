import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
import asyncio
from orchestrator import app as langgraph_app

async def main():
    state = {
        "status": None,
        "last_completed_node": None,
        "current_node": None,
        "retry_count": None,
        "next_retry": None,
        "approval_state": None,
        "llm_waiting_state": None,
        "validation_state": None,
        "security_state": None,
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
        "awaiting_approval": False,
        "confidence_score": 0.0,
        "dependency_graph": {},
    }
    
    astream_iter = langgraph_app.astream(state)
    while True:
        try:
            output = await anext(astream_iter, None)
            if output is None:
                break
            print("Yielded:", output.keys())
        except Exception as e:
            print("Error:", repr(e))
            break

if __name__ == "__main__":
    asyncio.run(main())
