import os
import re
import subprocess
from tools.safe_repo import safe_walk, safe_read_text, safe_path_exists, open_safe
import tempfile
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
from tools import context_cache


async def agent_repo_mapper(state: PipelineState):

    repo_url = state["repo_url"].strip()
    if repo_url.startswith("github.com/"):
        repo_url = "https://" + repo_url
        state["repo_url"] = repo_url

    # 0. Validate repo_url to prevent command injection and SSRF
    if not re.match(
        r"^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:\.git)?$", repo_url
    ):
        print(f"Invalid or unsafe repository URL: {repo_url}")
        return {"repo_local_path": "", "knowledge_graph": {}}

    temp_base = os.getenv("TEMP_REPO_PATH", "/tmp/repos")
    os.makedirs(temp_base, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="codesentinel_", dir=temp_base)

    try:
        github_token = os.getenv("GITHUB_TOKEN", "")
        clone_url = repo_url
        from tools.subprocess_runner import get_safe_env
        clone_env = get_safe_env(keep_github_token=True)
        clone_env["GIT_TERMINAL_PROMPT"] = "0"
        clone_env["GIT_ASKPASS"] = "echo"
        clone_env["GCM_INTERACTIVE"] = "false"  # Disable Windows Git Credential Manager GUI
        
        safe_env = get_safe_env(keep_github_token=False)

        try:
            if github_token and repo_url.startswith("https://github.com/"):
                clone_env["GIT_CONFIG_COUNT"] = "1"
                clone_env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
                clone_env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: bearer {github_token}"
                clone_env.pop("GITHUB_TOKEN", None)
                clone_env.pop("GH_TOKEN", None)
                subprocess.run(
                    ["git", "clone", "--no-checkout", clone_url, temp_dir],
                    check=True, timeout=300, env=clone_env, capture_output=True, text=True
                )
            else:
                subprocess.run(["git", "clone", "--no-checkout", clone_url, temp_dir], check=True, timeout=300, env=clone_env, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr or str(e)
            if github_token:
                err_msg = err_msg.replace(github_token, "***")
            raise RuntimeError(f"Clone failed: {err_msg}")

        commit_sha = state.get("commit_sha", "")
        if commit_sha:
            subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "checkout", commit_sha],
                cwd=temp_dir,
                check=True,
                timeout=30,
                env=safe_env,
                capture_output=True,
                text=True
            )
            print(f"[RepoMapper] Checked out commit {commit_sha}")
        else:
            subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "checkout"],
                cwd=temp_dir,
                check=True,
                timeout=30,
                env=safe_env,
                capture_output=True,
                text=True
            )
            print(f"[RepoMapper] Checked out default branch")

        try:
            res = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "ls-files"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=True,
                env=safe_env
            )
            tracked_files = set(res.stdout.splitlines())
        except subprocess.SubprocessError as e:
            print(f"Warning: Failed to get tracked files via git ls-files: {e}")
            tracked_files = None

    except Exception as e:
        print(f"Error cloning repository: {e}")
        return {"repo_local_path": "", "knowledge_graph": {}}

    # 2. Walk directory to find extensions, dependency files, and build context
    extensions = {}
    dep_files = []
    file_tree = []
    interesting_content = []

    api_db_keywords = [
        "app.route",
        "app.get",
        "app.post",
        "router.get",
        "router.post",
        "@GetMapping",
        "@PostMapping",
        "express()",
        "SQLAlchemy",
        "Prisma",
        "Mongoose",
        "db.query",
        "SELECT ",
        "UPDATE ",
    ]

    from config import IGNORED_DIRS

    for root, dirs, files, _ in safe_walk(temp_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        rel_root = os.path.relpath(root, temp_dir).replace("\\", "/")
        if rel_root != ".":
            file_tree.append(rel_root + "/")

        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), temp_dir).replace(
                "\\", "/"
            )
            if (
                tracked_files is not None
                and rel_path.replace("\\", "/") not in tracked_files
            ):
                continue

            ext = os.path.splitext(file)[1]
            if ext:
                extensions[ext] = extensions.get(ext, 0) + 1
            if file in [
                "requirements.txt",
                "package.json",
                "pom.xml",
                "build.gradle",
                "build.gradle.kts",
                "go.mod",
                "Cargo.toml",
            ]:
                dep_files.append(rel_path)

            file_tree.append("  " + file)

            if ext in [
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
            ]:
                try:
                    content = safe_read_text(temp_dir, rel_path, encoding="utf-8", errors="ignore", max_bytes=5000)
                    if any(k in content for k in api_db_keywords):
                        interesting_content.append(
                            f"--- File: {rel_path} ---\n{content[:1000]}..."
                        )
                except Exception as e:
                    print(f"Warning: Silent exception caught: {e}")

    if GROQ_API_KEYS:
        prompt = f"""Analyze the following repository data to build a rich knowledge graph.
File extensions: {extensions}
Dependency files: {dep_files}

Repository Structure:
{chr(10).join(file_tree[:100])} # Truncated to 100 items

Interesting Source Snippets (for API/DB extraction):
{chr(10).join(interesting_content[:15])}

Extract the following:
1. Primary 'language' and 'framework'.
2. 'modules': Service boundary detection (group files into logical modules like auth, database, api based on structure).
3. 'api_endpoints': List of objects with 'path', 'method', and 'handler_file'.
4. 'db_interactions': List of objects mapping files to ORM models or DB tables.
5. 'test_framework': The shell command to run the project's test suite (e.g. 'pytest', 'npm test', 'mvn test', 'go test ./...'). If unknown, use empty string.

Return ONLY valid JSON with keys: 'language', 'framework', 'modules', 'api_endpoints', 'db_interactions', 'test_framework'."""

        try:
            knowledge_graph = await invoke_llm(
                prompt,
                agent_name="repo_mapper",
                task_class="LIGHT",
                expect_json=True,
            )
            if not isinstance(knowledge_graph, dict) or knowledge_graph.get("error"):
                knowledge_graph = {
                    "language": "unknown",
                    "framework": "unknown",
                    "modules": [],
                    "api_endpoints": [],
                    "db_interactions": [],
                    "test_framework": "",
                }
        except Exception as e:
            print(f"[RepoMapper] LLM error: {e}")
            knowledge_graph = {
                "language": "unknown",
                "framework": "unknown",
                "modules": [],
                "api_endpoints": [],
                "db_interactions": [],
                "test_framework": "",
            }
    else:
        print("[RepoMapper] No LLM keys configured, proceeding with empty knowledge graph")
        knowledge_graph = {
            "language": "unknown",
            "framework": "unknown",
            "modules": [],
            "api_endpoints": [],
            "db_interactions": [],
            "test_framework": "",
        }

    # Build structural dependency graph (import parsing, cycle detection)
    dependency_graph = {}
    try:
        from tools.knowledge_graph import build_knowledge_graph
        from tools.vector_store import index_codebase
        import asyncio

        # RAG Authenticity: Asynchronously index the codebase for semantic retrieval
        rag_task = asyncio.create_task(asyncio.to_thread(index_codebase, repo_url, temp_dir))
        context_cache.store(repo_url, "rag_task", rag_task)

        kg = build_knowledge_graph(temp_dir)
        dependency_graph = kg.to_dict()

        knowledge_graph["dependency_graph_summary"] = {
            "node_count": dependency_graph.get("node_count", 0),
            "edge_count": dependency_graph.get("edge_count", 0),
            "cycles": dependency_graph.get("cycles", []),
            "service_boundaries": [
                {"service": sb["service"], "file_count": sb["file_count"]}
                for sb in dependency_graph.get("service_boundaries", [])
            ],
        }
        print(
            f"[RepoMapper] Built dependency graph: {dependency_graph.get('node_count', 0)} nodes, "
            f"{dependency_graph.get('edge_count', 0)} edges, "
            f"{len(dependency_graph.get('cycles', []))} cycles detected"
        )
    except Exception as e:
        print(f"[RepoMapper] Dependency graph build failed (non-fatal): {e}")

    context_cache.store(repo_url, "knowledge_graph", knowledge_graph)

    return {
        "repo_local_path": temp_dir,
        "knowledge_graph": knowledge_graph,
        "dependency_graph": dependency_graph,
    }
