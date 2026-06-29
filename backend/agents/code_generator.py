import os
import json
import difflib
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
from tools.prompt_cache import CODE_GENERATOR_SYSTEM
from tools.context_pruner import extract_function_context


def _smart_truncate(file_content: str, issue: dict, target_file: str) -> str:
    """Use context pruner to extract relevant code around the bug, falling back to truncation."""
    changed_lines = []
    # Try to extract line numbers from the issue
    if isinstance(issue, dict):
        if issue.get("line"):
            changed_lines = [int(issue["line"])]
        elif issue.get("affected_lines"):
            changed_lines = [int(x) for x in issue["affected_lines"]]

    if changed_lines:
        result = extract_function_context(file_content, changed_lines, target_file)
        if result and len(result) > 50:
            return result[:6000]

    # Fallback: if file is small enough, return it whole; otherwise truncate
    if len(file_content) <= 6000:
        return file_content
    return file_content[:6000] + "\n```\n[FILE TRUNCATED — showing first 6000 chars]\n"


async def agent_code_generator(state: PipelineState):
    repo_local_path = state.get("repo_local_path", "")
    repair_plan = state.get("repair_plan", [])
    investigated_issues = state.get("investigated_issues", [])
    patches = state.get("patches", [])
    retry_count = state.get("retry_count", 0)

    validation_results = state.get("validation_results", [])
    security_retry_context = state.get("security_retry_context", [])
    touched_symbols = state.get("touched_symbols", {})
    failure_context = ""
    if validation_results and not validation_results[-1].get("passed"):
        failure_context = (
            f"PREVIOUS PATCH FAILED TESTS. Logs: {validation_results[-1].get('logs')}"
        )
    elif security_retry_context:
        failure_context = f"PREVIOUS PATCH FAILED SECURITY VERIFICATION. Remaining vulnerability details: {json.dumps(security_retry_context)}"

    if state.get("approval_decision") == "rejected":
        print("[CodeGenerator] Repair plan was REJECTED by human. Skipping.")
        return {
            "patches": patches,
            "pr_error": "Repair plan was rejected by a human reviewer.",
        }

    if not repair_plan or not GROQ_API_KEYS:
        return {"patches": patches}

    new_patches = []

    # Extract failed issue IDs from validation/security results
    failed_issue_ids = set()
    if validation_results and not validation_results[-1].get("passed"):
        failed_issue_ids.update(
            validation_results[-1].get("failed_issue_ids", [])
        )
    if security_retry_context:
        for sec in security_retry_context:
            sec_file = sec.get("file", sec.get("path", ""))
            for i in investigated_issues:
                if sec_file and any(f == sec_file or f.endswith(sec_file) for f in i.get("affected_files", [])):
                    failed_issue_ids.add(i.get("id"))

    # We always retry if it's the first time or if the issue explicitly failed or was never patched
    for plan in repair_plan:
        issue_id = plan.get("issue_id")

        # Check if already patched successfully in previous attempts
        existing_patch = next(
            (p for p in patches if p.get("patch_id") == issue_id), None
        )
        if retry_count > 0 and existing_patch and existing_patch.get("applied"):
            # It was applied. Did it fail validation or security?
            if issue_id not in failed_issue_ids and not touched_symbols.get(issue_id, {}).get("last_failure_reason"):
                print(f"[CodeGenerator] Skipping already patched issue {issue_id}")
                new_patches.append(existing_patch)
                continue

        issue = next((i for i in investigated_issues if i.get("id") == issue_id), {})

        # Read the actual file content so the LLM can generate a precise fix
        target_file = ""
        file_content = ""
        affected = issue.get("affected_files", [])
        if affected:
            target_file = affected[0]
            full_path = os.path.join(repo_local_path, target_file)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", errors="ignore") as f:
                        file_content = f.read()
                except Exception as e:
                    print(f"Error reading file {full_path}: {e}")

        if not target_file:
            print(
                f"[CodeGenerator] No target file identified for issue {plan.get('issue_id')}. Skipping."
            )
            continue

        if not file_content:
            print(
                f"[CodeGenerator] Target file '{target_file}' is missing or empty. Skipping."
            )
            continue

        # Tier 2 — Code generation requires the 70b model for accurate patches.
        # Strict diff output via system prompt.
        touched = touched_symbols.get(plan.get("issue_id"))
        previous_attempt_context = ""
        if touched:
            previous_attempt_context = f"""
Previous attempt for this issue (already applied in the file):
Last Patch:
{touched.get('last_patch')}

Failure Reason:
{touched.get('last_failure_reason')}

Attempt Count: {touched.get('attempt_count')}
"""

        prompt = f"""{CODE_GENERATOR_SYSTEM}

Issue to fix: {plan.get('action')}
Original Issue Context: {json.dumps(issue)}
{failure_context}
{previous_attempt_context}

File path: {target_file}
Current file content:
```
{_smart_truncate(file_content, issue, target_file)}
```"""

        try:
            fixed_content = await invoke_llm(
                prompt,
                agent_name="code_generator",
                tier=2,
                expect_json=False,
            )

            if not fixed_content:
                print(f"[CodeGenerator] Empty response for {target_file}, skipping.")
                continue

            # Clean up any markdown wrappers the LLM may have added
            if fixed_content.startswith("```"):
                lines = fixed_content.split("\n")
                fixed_content = "\n".join(lines[1:])
            if fixed_content.endswith("```"):
                fixed_content = fixed_content[:-3].rstrip()

            patch_applied = False
            if file_content and repo_local_path:
                full_path = os.path.join(repo_local_path, target_file)

                from tools.patch_applier import apply_patch

                patch_result = apply_patch(fixed_content, repo_local_path, target_file)

                if patch_result["success"]:
                    print(
                        f"[CodeGenerator] Successfully applied patch to {target_file}"
                    )
                    patch_applied = True
                    # Read back the modified content to create a diff for the UI
                    with open(full_path, "r", errors="ignore") as f:
                        new_content = f.read()
                    diff = _generate_diff(file_content, new_content, target_file)
                    if not diff.strip():
                        diff = fixed_content

                    issue_id = plan.get("issue_id")
                    touched_symbols[issue_id] = {
                        "issue_id": issue_id,
                        "file_path": target_file,
                        "attempt_count": touched_symbols.get(issue_id, {}).get(
                            "attempt_count", 0
                        )
                        + 1,
                        "last_patch": fixed_content,
                        "last_failure_reason": None,
                    }
                else:
                    print(
                        f"[CodeGenerator] Patch failed to apply on {target_file}: {patch_result['stderr']}"
                    )
                    diff = fixed_content  # Show what the LLM generated even if it failed to apply

                    issue_id = plan.get("issue_id")
                    touched_symbols[issue_id] = {
                        "issue_id": issue_id,
                        "file_path": target_file,
                        "attempt_count": touched_symbols.get(issue_id, {}).get(
                            "attempt_count", 0
                        )
                        + 1,
                        "last_patch": fixed_content,
                        "last_failure_reason": f"Patch failed to apply: {patch_result['stderr']}",
                    }
            else:
                diff = fixed_content

            new_patches.append(
                {
                    "patch_id": plan.get("issue_id"),
                    "file": target_file,
                    "diff": diff,
                    "applied": patch_applied,
                }
            )
        except Exception as e:
            print(f"Error generating code: {e}")
            import traceback

            traceback.print_exc()

    # Remove previous failed patches for the same issues so we don't accumulate duplicates on retries
    current_issue_ids = [plan.get("issue_id") for plan in repair_plan]
    existing_patches = [
        p for p in patches if p.get("patch_id") not in current_issue_ids
    ]

    result = {
        "patches": existing_patches + new_patches,
        "touched_symbols": touched_symbols,
    }
    if repair_plan and not new_patches:
        result["pr_error"] = state.get(
            "pr_error",
            "Failed to generate code patches: API Rate Limit Exceeded or LLM failure.",
        )

    return result


def _generate_diff(old_content, new_content, filename):
    """Generate a unified diff string for display in the UI."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}"
    )
    return "".join(diff)
