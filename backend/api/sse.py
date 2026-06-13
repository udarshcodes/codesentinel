import json
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from orchestrator import app as langgraph_app

router = APIRouter()

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

async def event_generator(repo_url: str):
    # Initial state — provide sane defaults for all PipelineState fields
    state = {
        "repo_url": repo_url,
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
        "token_usage": {},
    }
    
    yield {
        "data": json.dumps({"event": "pipeline_started", "data": {"repo_url": repo_url}})
    }

    # Stream from LangGraph
    try:
        async for output in langgraph_app.astream(state):
            # output is a dict where key is node name and value is the state update
            for node_name, state_update in output.items():
                safe_update = make_serializable(state_update)
                
                event_data = {
                    "agent": node_name,
                    "status": "success",
                    "data": safe_update
                }
                
                if state_update.get("awaiting_approval"):
                    yield {
                        "data": json.dumps({
                            "event": "approval_required",
                            "data": {
                                "agent": node_name,
                                "fix": safe_update.get("repair_plan", [])
                            }
                        })
                    }
                    # We would break here in a real implementation to wait for POST /approve
                    # For phase 1 mock, we just continue
                
                yield {
                    "data": json.dumps({"event": "agent_complete", "data": event_data})
                }
                
        yield {
            "data": json.dumps({"event": "pipeline_complete", "data": {"status": "done"}})
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {
            "data": json.dumps({"event": "error", "data": {"error": str(e)}})
        }

@router.get("/stream")
async def stream_pipeline(repo_url: str, request: Request):
    return EventSourceResponse(event_generator(repo_url))