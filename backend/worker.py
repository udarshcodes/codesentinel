import os
import sys
import json
import asyncio
import httpx
from datetime import datetime

# Ensure backend module is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from orchestrator import app as langgraph_app

# The worker requires these environment variables
TASK_ID = os.environ.get("TASK_ID")
REPO_URL = os.environ.get("REPO_URL")
COMMIT_SHA = os.environ.get("COMMIT_SHA", "")
BACKEND_URL = os.environ.get("BACKEND_URL")

sequence_counter = 0

def make_serializable(obj):
    """Recursively convert non-serializable objects to strings."""
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)

async def post_event(status: str, event_name: str, data: dict):
    global sequence_counter
    sequence_counter += 1
    
    payload = {
        "sequence": sequence_counter,
        "status": status,
        "event": event_name,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{BACKEND_URL}/api/v1/job/{TASK_ID}/event",
                json=payload,
                timeout=10.0
            )
            if res.status_code != 200:
                print(f"Failed to post event {event_name}: {res.text}")
    except Exception as e:
        print(f"Exception posting event {event_name}: {e}")

async def run_worker():
    if not TASK_ID or not REPO_URL or not BACKEND_URL:
        print("Missing required environment variables (TASK_ID, REPO_URL, BACKEND_URL)")
        sys.exit(1)
        
    print(f"Starting worker for task {TASK_ID} on {REPO_URL}")
    await post_event("STARTING", "pipeline_started", {"repo_url": REPO_URL})

    state = {
        "task_id": TASK_ID,
        "repo_url": REPO_URL,
        "commit_sha": COMMIT_SHA,
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
    }

    final_pr_url = ""
    final_pr_error = ""
    final_confidence = 0.0
    validated_fixes = []

    try:
        astream_iter = langgraph_app.astream(state)
        
        while True:
            try:
                output = await anext(astream_iter, None)
            except Exception as e:
                print(f"LangGraph execution error: {e}")
                await post_event("FAILED", "error", {"error": str(e)})
                break
                
            if output is None:
                break
                
            for node_name, state_update in output.items():
                safe_update = make_serializable(state_update)

                if "pr_url" in safe_update:
                    final_pr_url = safe_update["pr_url"]
                if "pr_error" in safe_update:
                    final_pr_error = safe_update["pr_error"]
                if "confidence_score" in safe_update:
                    final_confidence = safe_update["confidence_score"]
                if "validation_results" in safe_update:
                    # Collect passed fixes to send to the backend's ChromaDB
                    for val in safe_update["validation_results"]:
                        if val.get("passed"):
                            validated_fixes.append({
                                "issue": val.get("issue_description", ""),
                                "patch": val.get("patch", ""),
                                "confidence": final_confidence
                            })

                # Determine high level status based on the agent running
                status = "RUNNING_SCANNERS"
                if node_name == "bug_investigator":
                    status = "AI_ANALYSIS"
                elif node_name == "patch_generator":
                    status = "GENERATING_PATCH"
                elif node_name == "validator":
                    status = "VALIDATING_PATCH"
                elif node_name == "pr_author":
                    status = "CREATING_PULL_REQUEST"
                    
                event_data = {
                    "agent": node_name,
                    "status": "success",
                    "data": safe_update,
                }
                print(f"Agent {node_name} completed.")
                await post_event(status, "agent_complete", event_data)

        # Finished
        print("Pipeline complete.")
        await post_event("COMPLETED", "pipeline_complete", {
            "status": "done",
            "pr_url": final_pr_url,
            "pr_error": final_pr_error,
            "confidence_score": final_confidence,
            "validated_fixes": validated_fixes
        })

    except Exception as e:
        print(f"Fatal worker crash: {e}")
        await post_event("FAILED", "error", {"error": str(e)})

if __name__ == "__main__":
    asyncio.run(run_worker())
