import os
import sys
import asyncio

_global_cancel_event = None
_global_main_task = None

def _trigger_fatal_lease_loss(res=None, path: str = "", stage: str = ""):
    print("FATAL: Worker lease lost (401/403/409). Terminating immediately.")
    if res:
        print(f"Diagnostic - Status: {res.status_code}")
        print(f"Diagnostic - Path: {path}")
        print(f"Diagnostic - Stage: {stage}")
        try:
            from tools.auth import TASK_ID, WORKER_ATTEMPT_ID
            print(f"Diagnostic - Task: {TASK_ID}")
            print(f"Diagnostic - Attempt ID: {WORKER_ATTEMPT_ID[:8]}...")
            body = res.json()
            # sanitize body just in case
            if "secret" in str(body).lower() or "token" in str(body).lower():
                print("Diagnostic - Response: [SANITIZED FOR SECRETS]")
            else:
                print(f"Diagnostic - Response: {body}")
        except Exception:
            print(f"Diagnostic - Response (text): {res.text[:200]}")
    from tools.auth import abort_lease
    abort_lease()
    if _global_cancel_event:
        _global_cancel_event.set()
    if _global_main_task:
        _global_main_task.cancel()
    import sys
    sys.exit(1)


from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from orchestrator import app as langgraph_app
from tools.llm_router import LLMExhaustionError

TASK_ID = os.environ.get("TASK_ID")
REPO_URL = os.environ.get("REPO_URL")
COMMIT_SHA = os.environ.get("COMMIT_SHA", "")
BACKEND_URL = os.environ.get("BACKEND_URL")
WORKER_ATTEMPT_ID = os.environ.get("WORKER_ATTEMPT_ID")
WORKER_SECRET = os.environ.get("WORKER_WEBHOOK_SECRET", "")

def validate_env():
    if not TASK_ID or not REPO_URL or not BACKEND_URL or not WORKER_ATTEMPT_ID:
        print("CRITICAL: Missing required environment variables (TASK_ID, REPO_URL, BACKEND_URL, WORKER_ATTEMPT_ID).")
        sys.exit(1)

    if not WORKER_SECRET and os.environ.get("ENVIRONMENT") == "production":
        print("CRITICAL: WORKER_WEBHOOK_SECRET missing in secured environments.")
        sys.exit(1)


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


from tools.auth import authenticated_post, authenticated_get


async def prepare_next_approval_cycle(state, node_name):
    """
    Authoritatively prepares the workflow state for a new approval cycle.
    Used for first, second, and all subsequent high-risk fixes.
    """
    repair_plan = state.get("repair_plan", [])
    pending_high_risk = [f for f in repair_plan if f.get("risk_level") == "high-risk" and f.get("status") == "pending"]
    if not pending_high_risk:
        return False, None, None
        
    current_fix = pending_high_risk[0]
    state["awaiting_approval"] = True
    state["status"] = "WAITING_FOR_APPROVAL"
    state["approval_state"] = "pending"
    state["approval_payload"] = current_fix
    import uuid
    cycle_id = str(uuid.uuid4())
    state["approval_cycle_id"] = cycle_id
    
    payload = {
        "status": "WAITING_FOR_APPROVAL",
        "pipeline_state": state,
    }
    
    event_data = {
        "agent": node_name,
        "fix": current_fix,
        "fix_id": current_fix.get("fix_id"),
        "approval_cycle_id": cycle_id,
        "status": "WAITING_FOR_APPROVAL"
    }
    
    return True, payload, event_data
async def post_event(status: str, event_name: str, data: dict):
    from tools.auth import WORKER_ATTEMPT_ID
    payload = {
        "status": status,
        "event": event_name,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "worker_attempt_id": WORKER_ATTEMPT_ID
    }

    try:
        path = f"/api/v1/job/{TASK_ID}/event"
        res = await authenticated_post(path, payload)
        
        if event_name == "pipeline_complete":
            print(f"DIAGNOSTIC - HTTP Status: {res.status_code}")
            print(f"DIAGNOSTIC - Path: {path}")
            print(f"DIAGNOSTIC - Task ID: {TASK_ID}")
            print(f"DIAGNOSTIC - Worker Attempt ID: {WORKER_ATTEMPT_ID}")
            try:
                body = res.json() if res.content else {}
                if "secret" in str(body).lower() or "token" in str(body).lower():
                    print("DIAGNOSTIC - Response: [SANITIZED FOR SECRETS]")
                else:
                    print(f"DIAGNOSTIC - Response: {body}")
            except Exception:
                print(f"DIAGNOSTIC - Response (text): {res.text[:200]}")
            print(f"DIAGNOSTIC - State Before: {status}")

        if res.status_code in (401, 403, 409):
             _trigger_fatal_lease_loss(res, path, f"post_event({event_name})")
        elif res.status_code != 200:
            print(f"Failed to post event {event_name}: {res.text}")
    except Exception as e:
        print(f"Exception posting event {event_name}: {e}")


async def heartbeat_loop(cancel_event: asyncio.Event, main_task: asyncio.Task):
    failures = 0
    while not cancel_event.is_set():
        try:
            await asyncio.sleep(30)
            if cancel_event.is_set():
                break
            path = f"/api/v1/job/{TASK_ID}/heartbeat"
            res = await authenticated_post(path, {})
            
            if res.status_code == 401:
                _trigger_fatal_lease_loss(res, path, "heartbeat - 401 Authentication Failure")
            elif res.status_code == 403:
                _trigger_fatal_lease_loss(res, path, "heartbeat - 403 HMAC/Authorization Failure")
            elif res.status_code == 409:
                _trigger_fatal_lease_loss(res, path, "heartbeat - 409 Stale Worker")
            elif res.status_code >= 500:
                print(f"Warning: Heartbeat failed with backend infrastructure error {res.status_code}")
                failures += 1
                if failures >= 3:
                    print("FATAL: Too many consecutive heartbeat backend failures (500). Terminating execution.")
                    cancel_event.set()
                    main_task.cancel()
                    break
            elif res.status_code != 200:
                print(f"Warning: Heartbeat failed with unexpected status {res.status_code}")
                failures += 1
                if failures >= 3:
                    print("FATAL: Too many consecutive heartbeat failures. Terminating execution.")
                    cancel_event.set()
                    main_task.cancel()
                    break
            else:
                failures = 0
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Warning: Heartbeat exception (network/infrastructure): {e}")
            failures += 1
            if failures >= 3:
                print("FATAL: Too many consecutive heartbeat exceptions. Terminating execution.")
                cancel_event.set()
                main_task.cancel()
                break

async def run_worker():
    validate_env()

    from tools.sandbox_runner import check_sandbox_capabilities
    check_sandbox_capabilities()

    print(f"Starting worker for task {TASK_ID} on {REPO_URL}")

    # Try to fetch existing pipeline state (this also validates the worker attempt!)
    existing_state = None
    fetch_attempts = 0
    while fetch_attempts < 3:
        try:
            state_res = await authenticated_get(f"/api/v1/job/{TASK_ID}/state")
            if state_res.status_code == 409:
                print("Stale worker attempt detected during startup. Exiting.")
                sys.exit(0)
            elif state_res.status_code == 200:
                data = state_res.json()
                status = data.get("status")
                if status in ["COMPLETED", "FAILED", "NEEDS_REVIEW"]:
                    print(f"Task is already in terminal state ({status}). Worker will not resume.")
                    sys.exit(0)

                existing_state = data.get("pipeline_state")
                approval_decision = data.get("approval_decision")
                
                # Pydantic schema may populate a fresh {} state with None values, making it truthy.
                # Check for actual progress (e.g. last_completed_node or status) to differentiate.
                has_meaningful_state = existing_state and (
                    existing_state.get("last_completed_node") or 
                    existing_state.get("knowledge_graph") or
                    existing_state.get("status")
                )
                
                if has_meaningful_state:
                    if approval_decision:
                        existing_state["approval_decision"] = approval_decision
                        if approval_decision == "rejected":
                            print("Approval was rejected. Worker will not resume.")
                            sys.exit(0)
                    print(f"Resuming task {TASK_ID} from saved state.")
                else:
                    existing_state = None
                break
            else:
                print(f"Warning: Failed to fetch state: HTTP {state_res.status_code}")
        except Exception as e:
            print(f"Warning: Failed to fetch state: {e}")
            
        fetch_attempts += 1
        if fetch_attempts < 3:
            await asyncio.sleep(2 ** fetch_attempts)
            
    if fetch_attempts >= 3 and not existing_state:
        print("CRITICAL: Failed to fetch state after 3 attempts. Terminating safely.")
        sys.exit(1)

    # Create a cancellation event for the heartbeat loop to signal the main execution
    cancel_event = asyncio.Event()
    
    # Start heartbeat after confirming we are the valid worker, passing the current task
    main_task = asyncio.current_task()
    heartbeat_task = asyncio.create_task(heartbeat_loop(cancel_event, main_task))

    await post_event("STARTING", "pipeline_started", {"repo_url": REPO_URL})

    if existing_state:
        state = existing_state
        if state.get("llm_waiting_state"):
            state["llm_waiting_state"] = False
            state.pop("last_llm_model", None)
            state.pop("last_llm_error", None)
            state.pop("last_llm_exhaustion_at", None)
            state.pop("next_retry", None)
        
        # Resume Safety (Req 10): Only pop approval fields if we explicitly resumed from an approval dispatch
        if state.get("approval_decision") in ("approved", "rejected"):
            state.pop("awaiting_approval", None)
            state.pop("approval_payload", None)
            state.pop("approval_decision", None)

        if not state.get("task_id"):
            state["task_id"] = TASK_ID
        if not state.get("repo_url"):
            state["repo_url"] = REPO_URL
        if not state.get("commit_sha"):
            state["commit_sha"] = COMMIT_SHA
            
        # Ensure all standard pipeline state keys exist to prevent KeyErrors
        # in older jobs or malformed state payloads.
        state.setdefault("knowledge_graph", {})
        state.setdefault("dependency_findings", [])
        state.setdefault("static_findings", [])
        state.setdefault("investigated_issues", [])
        state.setdefault("repair_plan", [])
        state.setdefault("patches", [])
        state.setdefault("validation_results", [])
        state.setdefault("security_verified", False)
        state.setdefault("pr_url", "")
        state.setdefault("pr_error", "")
        state.setdefault("retry_count", 0)
        state.setdefault("awaiting_approval", False)
        state.setdefault("confidence_score", 0.0)
        state.setdefault("dependency_graph", {})
        state.setdefault("last_completed_node", "")
            
        if not state.get("repo_url"):
            err_msg = "CRITICAL: Missing repo_url in resumed state, and REPO_URL fallback was empty."
            print(err_msg)
            await post_event("FAILED", "pipeline_error", {"error": err_msg})
            sys.exit(1)

        # Worker Resume: ALWAYS reconstruct workspace and do not trust persisted path
        print("Reconstructing workspace unconditionally for resumed job...")
        import tempfile
        import subprocess
        from tools.subprocess_runner import get_safe_env
        from tools.patch_applier import apply_patch
        
        temp_base = os.getenv("TEMP_REPO_PATH", "/tmp/repos")
        os.makedirs(temp_base, exist_ok=True)
        new_path = tempfile.mkdtemp(prefix="codesentinel_", dir=temp_base)
        
        _repo_url = state.get("repo_url")
        _commit_sha = state.get("commit_sha")
        
        if not _repo_url:
            raise ValueError("Cannot reconstruct workspace: missing REPO_URL.")
            
        try:
            if _repo_url in ["test", "test_repo", "http://repo"]:
                print("Bypassing workspace reconstruction for unit test.")
                state["repo_local_path"] = new_path
            else:
                from tools.subprocess_runner import clone_github_repo
                github_token = os.environ.get("GITHUB_TOKEN", "")
                clone_github_repo(_repo_url, new_path, github_token)
                    
                safe_env = get_safe_env(keep_github_token=False)
                subprocess.run(["git", "config", "core.hooksPath", "/dev/null"], cwd=new_path, check=True, env=safe_env)
                
                if _commit_sha:
                    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "checkout", _commit_sha], cwd=new_path, check=True, env=safe_env)
                    res_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=new_path, check=True, env=safe_env, capture_output=True, text=True)
                    if res_head.stdout.strip() != _commit_sha:
                        err_msg = "CRITICAL: Base commit mismatch during workspace reconstruction."
                        print(err_msg)
                        await post_event("FAILED", "pipeline_error", {"error": err_msg})
                        sys.exit(1)
                else:
                    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "checkout"], cwd=new_path, check=True, env=safe_env)
        except Exception as e:
            err_msg = f"CRITICAL: Failed to reconstruct workspace: {e}"
            print(err_msg)
            await post_event("FAILED", "pipeline_error", {"error": err_msg})
            sys.exit(1)
            
        # Re-apply patches to restore pipeline state
        for patch in state.get("patches", []):
            if isinstance(patch, dict) and patch.get("applied") and (patch.get("patch") or patch.get("patch_text") or patch.get("diff")) and patch.get("file"):
                try:
                    patch_content = patch.get("patch") or patch.get("patch_text") or patch.get("diff")
                    res = apply_patch(patch_content, new_path, patch["file"])
                    if not res.get("success"):
                        err_msg = f"CRITICAL: Failed to reapply patch during reconstruction: {res.get('stderr')}"
                        print(err_msg)
                        state["status"] = "FAILED"
                        state["pr_error"] = err_msg
                        await post_event("FAILED", "pipeline_error", {"error": err_msg})
                        sys.exit(1)
                except Exception as e:
                    err_msg = f"CRITICAL: Exception applying patch during reconstruction: {e}"
                    print(err_msg)
                    state["status"] = "FAILED"
                    state["pr_error"] = err_msg
                    await post_event("FAILED", "pipeline_error", {"error": err_msg})
                    sys.exit(1)
        
        state["repo_local_path"] = new_path
    else:
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
            "last_completed_node": "",
        }

    final_pr_url = ""
    final_pr_error = ""
    final_confidence = 0.0
    validated_fixes = []

    try:
        print(f"[Diag] astream_before: task_id={TASK_ID}, status={state.get('status', 'N/A')}, last_completed_node={state.get('last_completed_node', '')}, repo_url_present={bool(state.get('repo_url'))}, dep_findings={len(state.get('dependency_findings', []))}, static_findings={len(state.get('static_findings', []))}, patches={len(state.get('patches', []))}, validations={len(state.get('validation_results', []))}")
        astream_iter = langgraph_app.astream(state)

        fatal_error = False

        while not cancel_event.is_set():
            try:
                # Safely wait for the next graph update without cancelling it prematurely
                anext_task = asyncio.create_task(anext(astream_iter, None))
                while not anext_task.done():
                    if cancel_event.is_set():
                        anext_task.cancel()
                        break
                    await asyncio.sleep(1.0)
                
                if cancel_event.is_set():
                    break
                    
                output = anext_task.result()
                
            except LLMExhaustionError:
                raise
            except StopAsyncIteration:
                output = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"LangGraph execution error: {e}")
                await post_event("FAILED", "pipeline_error", {"error": str(e)})
                fatal_error = True
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
                    _conf = safe_update.get("confidence_score", final_confidence)
                    for val in safe_update["validation_results"]:
                        if val.get("passed"):
                            validated_fixes.append(
                                {
                                    "issue": val.get("issue_description", ""),
                                    "patch": val.get("patch", ""),
                                    "confidence": _conf,
                                }
                            )


                current_stage = "RUNNING_SCANNERS"
                if node_name == "bug_investigator":
                    current_stage = "AI_ANALYSIS"
                elif node_name == "code_generator":
                    current_stage = "GENERATING_PATCH"
                elif node_name == "validator":
                    current_stage = "VALIDATING_PATCH"
                elif node_name == "pr_author":
                    current_stage = "CREATING_PULL_REQUEST"

                for k, v in safe_update.items():
                    if isinstance(v, list) and isinstance(state.get(k), list):
                        state[k].extend(v)
                    elif isinstance(v, dict) and isinstance(state.get(k), dict):
                        state[k].update(v)
                    else:
                        state[k] = v
                state["last_completed_node"] = node_name
                
                # Persist state back to SQLite
                try:
                    # state.pop("status", None) - removed to avoid stripping authoritative state
                    state["current_stage"] = current_stage
                    
                    # If approval is required, transition to WAITING_FOR_APPROVAL atomically
                    new_status = "WAITING_FOR_APPROVAL" if state.get("awaiting_approval") else "RUNNING"
                    
                    payload = {
                        "status": new_status,
                        "pipeline_state": state
                    }
                    res = await authenticated_post(f"/api/v1/job/{TASK_ID}/state", payload)
                    if res.status_code == 409:
                        print("Stale worker attempt detected during state save. Terminating.")
                        sys.exit(153)
                    elif res.status_code == 422:
                        print(f"Invalid state schema: {res.text}")
                        sys.exit(1)
                    elif res.status_code >= 500:
                        raise RuntimeError(f"Database/Backend failure: {res.text}")
                    elif res.status_code != 200:
                        raise RuntimeError(f"Failed to persist state: {res.text}")
                except Exception as e:
                    print(f"Failed to persist state after {node_name}: {e}")
                    # Do not emit pipeline_error to prevent false completions
                    sys.exit(1)

                # Extract crucial UI metadata for the frontend
                agent_metadata = {}
                if node_name == "dependency_analyzer":
                    findings = safe_update.get("dependency_findings", [])
                    outdated = [f for f in findings if "Outdated dependency" in f.get("issue", "")]
                    cves = [f for f in findings if "CVEs:" in f.get("issue", "")]
                    agent_metadata = {
                        "outdated_count": len(outdated),
                        "cve_count": len(cves)
                    }
                elif node_name == "static_analysis":
                    static_findings = safe_update.get("static_findings", [])
                    agent_metadata = {"vulnerability_count": len(static_findings)}
                elif node_name == "bug_investigator":
                    investigated = safe_update.get("investigated_issues", [])
                    agent_metadata = {"confirmed_issues": len(investigated)}
                elif node_name == "code_generator":
                    patches = safe_update.get("patches", [])
                    agent_metadata = {"patches_generated": len(patches)}

                event_data = {
                    "agent": node_name,
                    "status": "success",
                    "metadata": agent_metadata,
                    "current_stage": current_stage,
                }
                if "error" in safe_update:
                    event_data["error"] = safe_update["error"]
                if "pipeline_error" in safe_update:
                    event_data["error"] = safe_update["pipeline_error"]

                print(f"Agent {node_name} completed.")
                await post_event("RUNNING", "agent_complete", event_data)

                # Check if approval is required and pause execution if so.
                if node_name in ["repair_planner", "code_generator"]:
                    print(f"Worker checking for human approval after {node_name}.")
                    
                    needs_approval, payload, event_data = await prepare_next_approval_cycle(state, node_name)
                    if not needs_approval:
                        state["awaiting_approval"] = False
                        continue
                        
                    success = False
                    for attempt in range(3):
                        try:
                            res = await authenticated_post(f"/api/v1/job/{TASK_ID}/state", payload)
                            if res.status_code == 200:
                                success = True
                                break
                            elif res.status_code == 409:
                                print("STALE_WORKER detected during approval save. Terminating.")
                                sys.exit(153)
                            elif res.status_code in (400, 422):
                                print(f"Invalid approval state payload: {res.text}")
                                sys.exit(1)
                            print(f"Approval persistence attempt {attempt + 1} failed: HTTP {res.status_code} - {res.text}")
                        except Exception as e:
                            print(f"Approval persistence attempt {attempt + 1} failed: {e}")
                        
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            
                    if not success:
                        print("CRITICAL: Failed to persist WAITING_FOR_APPROVAL state. Terminating safely.")
                        sys.exit(1)
                    
                    await post_event("WAITING_FOR_APPROVAL", "approval_required", event_data)
                    return

        if cancel_event.is_set():
            print("FATAL: Worker execution cancelled due to fatal heartbeat failures.")
            sys.exit(1)

        if not fatal_error and state.get("status") not in ["WAITING_FOR_LLM_CAPACITY", "WAITING_FOR_APPROVAL"]:
            print("Pipeline complete.")
            
            # Cancel the heartbeat loop immediately before completing
            # to avoid a race condition where a heartbeat arrives after the DB is COMPLETED,
            # which would result in a 409 rejection and fatal worker exit.
            cancel_event.set()
            heartbeat_task.cancel()
            
            await post_event(
                "COMPLETED",
                "pipeline_complete",
                {
                    "pr_url": final_pr_url,
                    "pr_error": final_pr_error,
                    "confidence_score": final_confidence,
                    "validated_fixes": validated_fixes,
                },
            )

        if fatal_error:
            print("Worker terminating due to fatal LangGraph error.")
            sys.exit(1)

    except LLMExhaustionError as e:
        print(f"LLM Capacity Exhausted: {e}")
        state["status"] = "WAITING_FOR_LLM_CAPACITY"
        state["pr_error"] = str(e)
        
        state["last_llm_model"] = e.model
        state["last_llm_error"] = e.last_error
        state["last_llm_exhaustion_at"] = datetime.now(timezone.utc).isoformat()
        
        llm_payload = {
            "pipeline_state": state,
            "retry_count": state.get("retry_count", 0),
            "next_retry": (datetime.now(timezone.utc) + timedelta(seconds=e.reset_time if e.reset_time is not None else 300)).isoformat(),
            "model": e.model if e.model else "unknown",
            "error": str(e) if str(e) else "Capacity Exhausted",
            "reset_time": e.reset_time
        }
        
        success = False
        for attempt in range(3):
            try:
                res = await authenticated_post(f"/api/v1/job/{TASK_ID}/llm-exhaustion", llm_payload)
                if res.status_code == 200:
                    success = True
                    break
                elif res.status_code == 409:
                    print("STALE_WORKER detected during exhaustion save. Terminating.")
                    sys.exit(153)
                elif res.status_code == 422:
                    print(f"Invalid llm-exhaustion schema: {res.text}")
                    sys.exit(1)
                print(f"Exhaustion persistence attempt {attempt + 1} failed: HTTP {res.status_code} - {res.text}")
            except Exception as state_err:
                print(f"Exhaustion persistence attempt {attempt + 1} failed: {state_err}")
            
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                
        if not success:
            print("CRITICAL: Failed to persist WAITING_FOR_LLM_CAPACITY state after 3 attempts.")
            sys.exit(1)
            
        sys.exit(0)

    except Exception as e:
        print(f"Fatal worker exception: {e}")
        await post_event("FAILED", "pipeline_error", {"error": str(e)})
        # Make sure to exit 1 so GitHub Actions correctly reports a failure
        sys.exit(1)

    finally:
        if 'heartbeat_task' in locals():
            heartbeat_task.cancel()
            
        # Cleanup temporary repository and sandbox workspaces after successful analysis,
        # failed analysis, timeout, worker cancellation, lease loss, exception, or retry exhaustion.
        if 'state' in locals() and state.get('repo_local_path'):
            import shutil
            repo_local_path = state.get('repo_local_path')
            if os.path.exists(repo_local_path):
                print(f"Cleaning up temporary repository workspace: {repo_local_path}")
                shutil.rmtree(repo_local_path, ignore_errors=True)

if __name__ == "__main__":
    validate_env()
    asyncio.run(run_worker())
