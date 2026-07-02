import os
import json
import asyncio
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.vector_store import query_similar_fixes
from tools.llm_router import invoke_llm
from tools import context_cache
from tools.prompt_cache import BUG_INVESTIGATOR_SYSTEM


async def agent_bug_investigator(state: PipelineState):
    repo_url = state.get("repo_url", "")
    repo_local_path = state.get("repo_local_path", "")
    static_findings = state.get("static_findings", [])
    dependency_findings = state.get("dependency_findings", [])

    all_findings = static_findings + dependency_findings
    investigated_issues = []

    if not GROQ_API_KEYS:
        return {"investigated_issues": investigated_issues}

    # If static analysis found nothing, fallback to a general LLM code review of primary files
    if not all_findings:
        print("No static findings, falling back to deep LLM code review...")
        source_files = []
        for root, _, files in os.walk(repo_local_path):
            if ".git" in root or "node_modules" in root or "__pycache__" in root:
                continue
            for file in files:
                if file.endswith(
                    (
                        ".py",
                        ".js",
                        ".ts",
                        ".jsx",
                        ".tsx",
                        ".go",
                        ".java",
                        ".rs",
                        ".html",
                        ".css",
                    )
                ):
                    source_files.append(os.path.join(root, file))

        # Limit to 5 files to avoid massive context
        for file_path in source_files[:5]:
            try:
                with open(file_path, "r", errors="ignore") as f:
                    content = f.read()
                rel_path = os.path.relpath(file_path, repo_local_path).replace(
                    "\\", "/"
                )

                prompt = f"""{BUG_INVESTIGATOR_SYSTEM}

Review the following file for any LOGICAL BUGS, SYNTAX ERRORS, UNDEFINED VARIABLES, MEMORY LEAKS, N+1 DATABASE QUERY PATTERNS, or INEFFICIENT LOOPS.
File: {rel_path}

Content:
```
{content[:5000]}
```

If you find a bug, return valid JSON: {{"found": true, "id": 1, "description": "...", "root_cause": "...", "severity": "...", "affected_files": ["..."]}}
If no bugs, return: {{"found": false}}"""

                # Tier 1 for initial scanning, will auto-escalate on failure
                result = await invoke_llm(
                    prompt,
                    agent_name="bug_investigator",
                    tier=1,
                    expect_json=True,
                )

                if isinstance(result, dict) and result.get("found"):
                    result.pop("found", None)
                    result["original_finding"] = {
                        "issue": result.get("description"),
                        "file": rel_path,
                    }
                    result["id"] = len(investigated_issues) + 100
                    if "category" not in result:
                        result["category"] = "functional"
                    investigated_issues.append(result)
            except Exception as e:
                print(f"Error in deep review: {e}")

        return {"investigated_issues": investigated_issues}

    for idx, finding in enumerate(all_findings):
        issue_desc = finding.get("issue", str(finding))
        file_path = finding.get("file", "")

        file_content = ""
        if file_path and repo_local_path:
            full_path = os.path.join(repo_local_path, file_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", errors="ignore") as f:
                        file_content = f.read()
                except Exception as e:
                    print(f"Error reading file {full_path}: {e}")

        line_num = finding.get("line")
        if file_content and line_num:
            from tools.context_pruner import extract_function_context

            pruned_content = extract_function_context(
                file_content, [line_num], file_path
            )
        else:
            pruned_content = file_content[:3000]

        # Query ChromaDB for past successful fixes in a background thread to prevent blocking
        past_context = await asyncio.to_thread(query_similar_fixes, issue_desc)
        past_context_str = (
            "\n".join(
                [f'Past fix for similar issue:\n{f["patch"]}' for f in past_context]
            )
            if past_context
            else "None"
        )

        # Use localized graph instead of full knowledge graph
        localized_graph = context_cache.get_localized_graph(repo_url, file_path)

        prompt = f"""{BUG_INVESTIGATOR_SYSTEM}

Analyze the following finding:
Issue: {issue_desc}
File: {file_path}

File Content:
```
{pruned_content}
```

Repository Context: {json.dumps(localized_graph)}
Past similar fixes for context: {past_context_str}

Determine the root cause, severity ("low", "medium", "high"), impact, and affected files.
Return ONLY valid JSON: {{"id": {idx}, "description": "...", "root_cause": "...", "severity": "...", "impact": "...", "affected_files": ["..."]}}"""

        try:
            # Tier 1 for investigation, auto-escalates on validation failure
            issue_data = await invoke_llm(
                prompt,
                agent_name="bug_investigator",
                tier=1,
                expect_json=True,
            )
            if isinstance(issue_data, dict) and not issue_data.get("error"):
                issue_data["original_finding"] = finding
                investigated_issues.append(issue_data)
        except Exception as e:
            print(f"Error investigating issue {idx}: {e}")

    return {"investigated_issues": investigated_issues}
