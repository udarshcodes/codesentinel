import os
import tempfile
from models.pipeline_state import PipelineState
from config import GROQ_API_KEYS
from tools.llm_router import invoke_llm
from tools import context_cache


async def agent_repo_mapper(state: PipelineState):
    import re

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

    # 1. Clone repository
    temp_base = os.getenv("TEMP_REPO_PATH", "/tmp/repos")
    os.makedirs(temp_base, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="codesentinel_", dir=temp_base)

    import subprocess

    try:
        github_token = os.getenv("GITHUB_TOKEN", "")
        clone_url = repo_url
        if github_token and repo_url.startswith("https://github.com/"):
            clone_url = repo_url.replace(
                "https://github.com/", f"https://oauth2:{github_token}@github.com/"
            )

        subprocess.run(["git", "clone", clone_url, temp_dir], check=True, timeout=300)

        # If a specific commit SHA was requested (e.g., from CI/CD), checkout that commit
        commit_sha = state.get("commit_sha", "")
        if commit_sha:
            subprocess.run(
                ["git", "checkout", commit_sha], cwd=temp_dir, check=True, timeout=30
            )
            print(f"[RepoMapper] Checked out commit {commit_sha}")

        try:
            res = subprocess.run(
                ["git", "ls-files"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            tracked_files = set(res.stdout.splitlines())
        except Exception:
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

    for root, dirs, files in os.walk(temp_dir):
        if (
            ".git" in root
            or "node_modules" in root
            or "venv" in root
            or "__pycache__" in root
        ):
            continue

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

            # Extract content for API and DB mapping if it's a source file
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
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        content = f.read(5000)  # Read up to 5000 chars to save context
                        if any(k in content for k in api_db_keywords):
                            interesting_content.append(
                                f"--- File: {rel_path} ---\n{content[:1000]}..."
                            )
                except Exception:
                    pass

    # 3. LLM analysis — Tier 1 (extracting rich knowledge graph)
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
                tier=1,
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
        knowledge_graph = {
            "language": "Python (Mock)",
            "framework": "FastAPI",
            "modules": [],
            "api_endpoints": [],
            "db_interactions": [],
            "test_framework": "pytest",
        }

    # Build structural dependency graph (import parsing, cycle detection)
    dependency_graph = {}
    try:
        from tools.knowledge_graph import build_knowledge_graph

        kg = build_knowledge_graph(temp_dir)
        dependency_graph = kg.to_dict()

        # Merge structural data into the knowledge_graph for downstream agents
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

    # Cache the knowledge graph for downstream agents
    context_cache.store(repo_url, "knowledge_graph", knowledge_graph)

    return {
        "repo_local_path": temp_dir,
        "knowledge_graph": knowledge_graph,
        "dependency_graph": dependency_graph,
    }
