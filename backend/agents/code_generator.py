import os
import json
import difflib
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
import subprocess
from tools.prompt_cache import CODE_GENERATOR_SYSTEM

async def agent_code_generator(state: PipelineState):
    repo_local_path = state.get("repo_local_path", "")
    repair_plan = state.get("repair_plan", [])
    investigated_issues = state.get("investigated_issues", [])
    patches = state.get("patches", [])
    retry_count = state.get("retry_count", 0)
    
    validation_results = state.get("validation_results", [])
    failure_context = ""
    if validation_results and not validation_results[-1].get("passed"):
        failure_context = f"PREVIOUS PATCH FAILED. Logs: {validation_results[-1].get('logs')}"

    if not repair_plan or not GROQ_API_KEYS:
        return {"patches": patches}
    
    new_patches = []
    for plan in repair_plan:
        issue = next((i for i in investigated_issues if i.get("id") == plan.get("issue_id")), {})
        
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
                except Exception:
                    pass
        
        if not target_file:
            target_file = "main.py"
            
        if not file_content:
            print(f"[CodeGenerator] Target file '{target_file}' is missing or empty. Skipping.")
            continue
        
        # Tier 2 — Code generation requires the 70b model for accurate patches.
        # Strict diff output via system prompt.
        prompt = f"""{CODE_GENERATOR_SYSTEM}

Issue to fix: {plan.get('action')}
Original Issue Context: {json.dumps(issue)}
{failure_context}

File path: {target_file}
Current file content:
```
{file_content[:4000]}
```"""
        
        try:
            fixed_content = invoke_llm(
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
            
            if file_content and repo_local_path:
                full_path = os.path.join(repo_local_path, target_file)
                
                # Write the unified diff to a temporary file
                patch_path = os.path.join(repo_local_path, "temp.patch")
                with open(patch_path, "w") as f:
                    f.write(fixed_content)
                    
                # Apply the patch using the patch command
                try:
                    subprocess.run(["patch", "-p1", "-i", "temp.patch"], cwd=repo_local_path, check=True, capture_output=True)
                    print(f"[CodeGenerator] Successfully applied patch to {target_file}")
                    
                    # Read back the modified content to create a diff for the UI
                    with open(full_path, "r", errors="ignore") as f:
                        new_content = f.read()
                    diff = _generate_diff(file_content, new_content, target_file)
                except subprocess.CalledProcessError as e:
                    print(f"[CodeGenerator] Patch failed to apply on {target_file}: {e.stderr}")
                    diff = fixed_content # Show what the LLM generated even if it failed to apply
                finally:
                    if os.path.exists(patch_path):
                        os.remove(patch_path)
            else:
                diff = fixed_content
            
            new_patches.append({
                "patch_id": plan.get("issue_id"),
                "file": target_file,
                "diff": diff,
                "applied": True
            })
        except Exception as e:
            print(f"Error generating code: {e}")
            import traceback
            traceback.print_exc()
            
    result = {"patches": patches + new_patches}
    if repair_plan and not new_patches:
        result["pr_error"] = state.get("pr_error", "Failed to generate code patches: API Rate Limit Exceeded or LLM failure.")
        
    return result


def _generate_diff(old_content, new_content, filename):
    """Generate a unified diff string for display in the UI."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}")
    return "".join(diff)