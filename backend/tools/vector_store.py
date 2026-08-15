import os
import hashlib
import chromadb

CHROMA_PERSIST_PATH = os.getenv(
    "CHROMA_PERSIST_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chroma_data"),
)
client = None
fixes_collection = None


def _get_collections():
    global client, fixes_collection
    if client is None:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)
        fixes_collection = client.get_or_create_collection("validated_fixes")
    return client, fixes_collection


def store_validated_fix(repo_url: str, issue_description: str, patch: str, confidence: float):
    # RAG FLOW (Ingest & Store): Fixes are embedded globally but scoped strictly by repo_url metadata
    # This prevents cross-tenant data leakage while allowing the system to learn from successful fixes within the same repository.
    try:
        _, fixes = _get_collections()
        doc_id = f"fix_{hashlib.sha256((repo_url + issue_description + patch).encode()).hexdigest()[:16]}"
        fixes.upsert(
            documents=[issue_description],
            metadatas=[{"repo_url": repo_url, "patch": patch, "confidence": confidence}],
            ids=[doc_id],
        )
    except Exception as e:
        print(f"Error storing validated fix: {e}")


def query_similar_fixes(repo_url: str, issue_description: str, n_results: int = 3) -> list:
    # RAG FLOW (Retrieve): Only fetch similar fixes for this exact repository.
    # The where={"repo_url": repo_url} filter enforces the security boundary to prevent cross-contamination.
    try:
        _, fixes = _get_collections()
        results = fixes.query(
            query_texts=[issue_description], 
            n_results=n_results,
            where={"repo_url": repo_url}
        )
        found_fixes = []
        if not results.get("documents") or not results["documents"][0]:
            return found_fixes

        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            found_fixes.append(
                {"issue": doc, "patch": meta["patch"], "confidence": meta["confidence"]}
            )
        return found_fixes
    except Exception as e:
        print(f"Error querying similar fixes: {e}")
        return []

def index_codebase(repo_url: str, repo_local_path: str):
    # TRUE RAG (Ingest & Store): Chunks and embeds the actual repository code into a dedicated codebase collection.
    # This ensures the Bug Investigator LLM has semantic access to the entire repository, not just past fixes.
    try:
        client, _ = _get_collections()
        # Use a deterministic collection name per repo to fully isolate vector spaces
        repo_safe = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
        collection = client.get_or_create_collection(f"codebase_{repo_safe}")
        
        docs = []
        metadatas = []
        ids = []
        
        for root, _, files in os.walk(repo_local_path):
            if ".git" in root or "node_modules" in root or "venv" in root:
                continue
            for file in files:
                if not file.endswith((".py", ".js", ".ts", ".go", ".java", ".rs")):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_local_path)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Simple chunking: 100 lines per chunk
                        lines = content.splitlines()
                        for i in range(0, len(lines), 100):
                            chunk = "\\n".join(lines[i:i+100])
                            if not chunk.strip():
                                continue
                            docs.append(chunk)
                            metadatas.append({"file": rel_path, "repo_url": repo_url})
                            ids.append(f"{rel_path}_{i}")
                except Exception:
                    pass
                    
        if docs:
            # Upsert in batches to respect sqlite limits
            batch_size = 100
            for i in range(0, len(docs), batch_size):
                collection.upsert(
                    documents=docs[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )
    except Exception as e:
        print(f"Error indexing codebase: {e}")

def query_codebase(repo_url: str, query: str, n_results: int = 3) -> list:
    # TRUE RAG (Retrieve): Fetches relevant code snippets directly from the embedded repository files.
    try:
        client, _ = _get_collections()
        repo_safe = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
        # Get collection without auto-create to avoid polluting DB if it wasn't indexed
        try:
            collection = client.get_collection(f"codebase_{repo_safe}")
        except Exception:
            return []
            
        results = collection.query(query_texts=[query], n_results=n_results)
        if not results.get("documents") or not results["documents"][0]:
            return []
            
        snippets = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            snippets.append({"file": meta["file"], "content": doc})
        return snippets
    except Exception as e:
        print(f"Error querying codebase: {e}")
        return []
