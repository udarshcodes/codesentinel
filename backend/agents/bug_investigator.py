import os
import json
import re
from typing import Dict, Any, List

from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.safe_repo import safe_walk, safe_read_text, safe_path_exists, open_safe

from tools.llm_router import invoke_llm
from tools import context_cache
from tools.prompt_cache import BUG_INVESTIGATOR_SYSTEM
from tools.vector_store import query_similar_fixes, query_codebase


async def agent_bug_investigator(state: PipelineState):
    repo_url = state.get("repo_url", "")
    repo_local_path = state.get("repo_local_path", "")
    static_findings = state.get("static_findings", [])
    dependency_findings = state.get("dependency_findings", [])

    all_findings = static_findings + dependency_findings
    investigated_issues = []
    
    rag_task = context_cache.get(repo_url, "rag_task")
    if rag_task:
        try:
            rag_status = await rag_task
            state["rag_status"] = rag_status
        except Exception as e:
            rag_status = {"status": "error", "error": str(e)}
            state["rag_status"] = rag_status
    else:
        rag_status = state.get("rag_status", {})
    if rag_status.get("status") == "success":
        print(f"[BugInvestigator] Repository RAG available: {rag_status.get('documents_indexed')} chunks indexed.")
    else:
        print(f"[BugInvestigator] Repository RAG UNAVAILABLE or failed: {rag_status.get('error', 'Not indexed')}")

    if not GROQ_API_KEYS:
        return {"investigated_issues": investigated_issues}

    if not all_findings:
        print("No static findings, falling back to deep LLM code review...")
        source_files = []
        for root, dirs, files, _ in safe_walk(repo_local_path):
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

        # Prevent context overflow by limiting file count
        for file_path in source_files[:5]:
            try:
                with open_safe(repo_local_path, file_path, "r", errors="ignore") as f:
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
                    task_class="LIGHT",
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
            try:
                file_content = safe_read_text(repo_local_path, file_path, errors="ignore", max_bytes=500000)
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")

        line_num = finding.get("line")
        if file_content and line_num:
            from tools.context_pruner import extract_function_context

            pruned_content = extract_function_context(
                file_content, [line_num], file_path
            )
        else:
            pruned_content = file_content[:3000]

        localized_graph = context_cache.get_localized_graph(repo_url, file_path)
        
        # RAG Authenticity: Fetch strictly isolated past fixes for this repository
        similar_fixes = query_similar_fixes(repo_url, issue_desc)
        if similar_fixes:
            similar_fixes_context = (
                "\\nSimilar Past Fixes from Knowledge Base:\\n"
                + json.dumps(similar_fixes, indent=2)
            )
        else:
            similar_fixes_context = "\\nSimilar Past Fixes from Knowledge Base: No relevant historical fixes retrieved."
            
        # TRUE RAG: Fetch codebase context semantically
        codebase_snippets = query_codebase(repo_url, issue_desc)
        if codebase_snippets:
            codebase_context = (
                "\\nSemantic Codebase Context:\\n"
                + json.dumps(codebase_snippets, indent=2)
            )
        else:
            codebase_context = "\\nSemantic Codebase Context: No relevant repository code retrieved."
            
        print(f"\\n--- RAG Retrieval Started ---")
        print(f"Repository: {repo_url}")
        print(f"Repository chunks retrieved: {len(codebase_snippets)}")
        if codebase_snippets:
            files_retrieved = list(set([s['file'] for s in codebase_snippets]))
            print(f"Files: {', '.join(files_retrieved)}")
        print(f"Historical fixes retrieved: {len(similar_fixes)}")
        print(f"RAG context injected into Bug Investigator\\n-----------------------------")

        prompt = f"""{BUG_INVESTIGATOR_SYSTEM}

Analyze the following finding:
Issue: {issue_desc}
File: {file_path}

File Content:
```
{pruned_content}
```

Repository Context: {json.dumps(localized_graph)}
{codebase_context}
{similar_fixes_context}

Determine the root cause, severity ("low", "medium", "high"), impact, and affected files.
Return ONLY valid JSON: {{"id": {idx}, "description": "...", "root_cause": "...", "severity": "...", "impact": "...", "affected_files": ["..."]}}"""

        try:
            # Tier 1 for investigation, auto-escalates on validation failure
            issue_data = await invoke_llm(
                prompt,
                agent_name="bug_investigator",
                task_class="LIGHT",
                expect_json=True,
            )
            if isinstance(issue_data, dict) and not issue_data.get("error"):
                issue_data["original_finding"] = finding
                investigated_issues.append(issue_data)
        except Exception as e:
            print(f"Error investigating issue {idx}: {e}")

    return {"investigated_issues": investigated_issues}
