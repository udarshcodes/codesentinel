import os
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
from tools.confidence_calc import calculate_pipeline_confidence
from tools.subprocess_runner import run_isolated_subprocess


async def agent_pr_author(state: PipelineState):
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    repo_url = state.get("repo_url", "")
    security_verified = state.get("security_verified", False)

    if state.get("approval_decision") in ("rejected", "EXPIRED"):
        return {
            "pr_url": "",
            "confidence_score": _calculate_confidence(state, security_verified),
            "pr_error": f"Repair plan was {state.get('approval_decision')}.",
        }

    patches = state.get("patches", [])
    if not patches:
        existing_error = state.get("pr_error")
        error_msg = (
            existing_error
            if existing_error
            else "No bugs were found or no patches were generated, so no PR is needed."
        )
        return {
            "pr_url": "",
            "confidence_score": _calculate_confidence(state, security_verified),
            "pr_error": error_msg,
        }

    if not any(patch.get("applied") and patch.get("file") for patch in patches):
        return {
            "pr_url": "",
            "pr_error": "No valid code changes were generated: all patch attempts were rejected.",
            "confidence_score": _calculate_confidence(state, security_verified),
        }

    # Determine state: was validation or security failed?
    latest = state.get("validation_results", [])[-1] if state.get("validation_results") else {}
    validation_failed = latest.get("passed") is not True or latest.get("tests_executed") is False or latest.get("build_failed", False) or latest.get("suite_failed", False)
    failed_ids = latest.get("failed_issue_ids", [])
    if failed_ids and len(failed_ids) >= len(patches):
        validation_failed = True

    if validation_failed or not security_verified or state.get("scanners_failed"):
        # State machine dictates we NEVER create a successful PR here.
        # It goes to NEEDS_REVIEW / DRAFT
        needs_review = True
    else:
        needs_review = False

    pr_url = ""
    pr_error = ""
    material_files = None

    if GITHUB_TOKEN and "github.com" in repo_url:
        try:
            from tools.github_client import (
                prepare_repo_for_push,
                commit_and_push,
                open_pull_request,
                create_trusted_pr_workspace,
                check_token_permissions,
            )
            from tools.safe_path import resolve_safe_path
            import shutil

            # Preflight check
            check_token_permissions(repo_url, GITHUB_TOKEN)

            repo_local_path = state.get("repo_local_path", "")
            if not repo_local_path or not os.path.exists(repo_local_path):
                pr_error = "No local repo path found to commit changes from."
                return {
                    "pr_url": "",
                    "confidence_score": _calculate_confidence(state, security_verified),
                    "pr_error": pr_error,
                }

            # 1. Create fresh trusted workspace
            commit_sha = state.get("commit_sha", "")
            trusted_workspace = create_trusted_pr_workspace(repo_url, GITHUB_TOKEN, commit_sha)
            
            # Verify repository HEAD is the intended commit before applying patches
            if commit_sha:
                res_head = run_isolated_subprocess(["git", "rev-parse", "HEAD"], cwd=trusted_workspace)
                if res_head["stdout"].strip() != commit_sha:
                    shutil.rmtree(trusted_workspace, ignore_errors=True)
                    raise ValueError("Security Violation: Base commit mismatch before patch application")

            # 2. Prepare fork and branch on trusted workspace
            github_data = prepare_repo_for_push(repo_url, trusted_workspace, GITHUB_TOKEN)

            # 3. Add modified files
            files_to_commit = []
            for patch in patches:
                if patch.get("applied") and patch.get("file"):
                    files_to_commit.append(patch["file"])

            # 4. Transfer validated changes securely by reapplying the patch text
            from tools.patch_applier import apply_patch
            from tools.auth import is_lease_lost
            
            for patch in patches:
                if is_lease_lost():
                    shutil.rmtree(trusted_workspace, ignore_errors=True)
                    return {
                        "pr_url": "",
                        "confidence_score": _calculate_confidence(state, security_verified),
                        "pr_error": "Worker lease lost! Cannot apply patches.",
                    }
                patch_content = patch.get("patch_text") or patch.get("patch")
                if patch.get("applied"):
                    if not patch_content:
                        pr_error = "Patch re-application failed: Secure patch_text is missing. Please regenerate the patch."
                        shutil.rmtree(trusted_workspace, ignore_errors=True)
                        return {
                            "pr_url": "",
                            "confidence_score": _calculate_confidence(state, security_verified),
                            "pr_error": pr_error,
                        }
                    res = apply_patch(patch_content, trusted_workspace, patch["file"])
                    if not res.get("success"):
                        pr_error = f"Patch re-application failed on trusted workspace: {res.get('stderr')}"
                        shutil.rmtree(trusted_workspace, ignore_errors=True)
                        return {
                            "pr_url": "",
                            "confidence_score": _calculate_confidence(state, security_verified),
                            "pr_error": pr_error,
                        }

            # Check Git Diff Integrity (Block unexpected modifications) on the trusted workspace
            res_diff = run_isolated_subprocess(["git", "diff", "--name-only"], cwd=trusted_workspace)
            res_staged = run_isolated_subprocess(["git", "diff", "--staged", "--name-only"], cwd=trusted_workspace)
            
            all_modified = set()
            if res_diff["status"] == "SUCCESS" and res_diff["stdout"]:
                all_modified.update(res_diff["stdout"].strip().splitlines())
            if res_staged["status"] == "SUCCESS" and res_staged["stdout"]:
                all_modified.update(res_staged["stdout"].strip().splitlines())
                
            unexpected_files = [f for f in all_modified if f not in files_to_commit]
            if unexpected_files:
                shutil.rmtree(trusted_workspace, ignore_errors=True)
                pr_error = f"Git diff integrity check failed. Unexpected files modified: {', '.join(unexpected_files)}"
                return {
                    "pr_url": "",
                    "confidence_score": _calculate_confidence(state, security_verified),
                    "pr_error": pr_error,
                }

            if not all_modified:
                shutil.rmtree(trusted_workspace, ignore_errors=True)
                return {"pr_url": "", "pr_error": "No valid code changes were generated.",
                        "confidence_score": _calculate_confidence(state, security_verified)}

            material_files = sorted(all_modified)
            diff_result = run_isolated_subprocess(["git", "diff", "HEAD", "--stat"], cwd=trusted_workspace)
            title, desc = describe_material_changes(all_modified, diff_result.get("stdout", ""), needs_review)
            if state.get("scanner_notes"):
                desc += "\n\n### Scan coverage\n" + "\n".join(f"- {note}" for note in state["scanner_notes"])

            if needs_review:
                title = f"[NEEDS REVIEW] {title}"

            if is_lease_lost():
                shutil.rmtree(trusted_workspace, ignore_errors=True)
                return {
                    "pr_url": "",
                    "confidence_score": _calculate_confidence(state, security_verified),
                    "pr_error": "Worker lease lost! Cannot push PR.",
                }

            has_changes = commit_and_push(
                local_path=trusted_workspace,
                branch_name=github_data["branch_name"],
                message=title,
                push_repo_url=github_data["push_repo_url"],
                token=GITHUB_TOKEN,
                files=files_to_commit,
            )
            
            # Clean up trusted workspace
            shutil.rmtree(trusted_workspace, ignore_errors=True)

            if not has_changes:
                pr_error = "No bugs were detected, or no valid code changes were generated by the AI."
                return {
                    "pr_url": "",
                    "confidence_score": _calculate_confidence(state, security_verified),
                    "pr_error": pr_error,
                }

            # 4. Open PR
            if state.get("security_retry_context"):
                unresolved = state.get("security_retry_context", [])
                desc += "\n\n### ⚠️ Unresolved Security Risks\nThe following security issues could not be automatically verified/repaired after retries:\n"
                for u in unresolved:
                    desc += f"- **{u.get('severity', 'Risk')}**: {u.get('issue', str(u))}\n"

            pr_url = open_pull_request(
                repo_name=github_data["repo_name"],
                branch_name=github_data["branch_name"],
                title=title,
                body=desc,
                token=GITHUB_TOKEN,
                is_owner=github_data["is_owner"],
                user_login=github_data["user_login"],
                is_draft=needs_review, # Force draft if needs review
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            pr_error = str(e)
            print(f"GitHub API Error: {e}")
    else:
        if not GITHUB_TOKEN:
            pr_error = "GITHUB_TOKEN not set in .env"
        else:
            pr_error = "Not a GitHub URL"

    # Dynamic confidence score based on pipeline results
    confidence_score = _calculate_confidence(state, security_verified)

    result = {"pr_url": pr_url, "confidence_score": confidence_score}
    if material_files is not None:
        result["material_files"] = material_files
    if pr_error:
        result["pr_error"] = pr_error
    return result


def _calculate_confidence(state, security_verified):
    """
    Calculate unified dynamic confidence score (0-100).
    """
    existing_chroma = state.get("rag_confidence_score", 0.0)
    return calculate_pipeline_confidence(
        state, security_clean=security_verified, chroma_score=existing_chroma
    )


def describe_material_changes(files, diff_stat, needs_review):
    """Describe Git-observed changes rather than the model's intended plan."""
    paths = sorted(set(files))
    title = f"Automated changes to {paths[0]}" if len(paths) == 1 else f"Automated changes to {len(paths)} files"
    description = "This PR contains code changes. Review the diff to assess each proposed repair."
    if needs_review:
        description += "\n\nDraft: validation or security verification did not establish that these changes are safe to merge. Unresolved findings may remain."
    description += "\n\n### Modified files\n" + "\n".join(f"- `{path}`" for path in paths)
    description += "\n\n### Git diff summary\n```text\n" + diff_stat.strip() + "\n```"
    return title, description
