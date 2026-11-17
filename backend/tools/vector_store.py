import os
import hashlib
import threading
import chromadb
from tools.safe_repo import safe_walk, safe_read_text

CHROMA_PERSIST_PATH = os.getenv(
    "CHROMA_PERSIST_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chroma_data"),
)
client = None
fixes_collection = None
_client_lock = threading.RLock()


def close_vector_store():
    """Release SQLite handles before deleting a workspace or shutting down."""
    global client, fixes_collection
    if client is not None:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    client = None
    fixes_collection = None


def _get_collections():
    global client, fixes_collection
    with _client_lock:
        if client is None or fixes_collection is None:
            new_client = chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)
            new_fixes = new_client.get_or_create_collection("validated_fixes")
            client, fixes_collection = new_client, new_fixes
    return client, fixes_collection


def store_validated_fix(repo_url: str, issue_description: str, patch: str, confidence: float, *, strict=False):
    # RAG FLOW (Ingest & Store): Fixes are embedded globally but scoped strictly by repo_url metadata
    # This prevents cross-tenant data leakage while allowing the system to learn from successful fixes within the same repository.
    try:
        if not repo_url or not issue_description.strip() or not patch.strip():
            raise ValueError("Repository, issue and nonempty patch are required")
        _, fixes = _get_collections()
        doc_id = f"fix_{hashlib.sha256((repo_url + issue_description + patch).encode()).hexdigest()[:16]}"
        if fixes.get(ids=[doc_id])["ids"]:
            return
        fixes.upsert(
            documents=[issue_description],
            metadatas=[{"repo_url": repo_url, "patch": patch, "confidence": confidence}],
            ids=[doc_id],
        )
    except Exception as e:
        if strict:
            raise
        print(f"Error storing validated fix: {e}")


def query_similar_fixes(repo_url: str, issue_description: str, n_results: int = 3, *, strict=False) -> list:
    # RAG FLOW (Retrieve): Only fetch similar fixes for this exact repository.
    # The where={"repo_url": repo_url} filter enforces the security boundary to prevent cross-contamination.
    try:
        _, fixes = _get_collections()
        if not fixes.count():
            return []
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
        if strict:
            raise
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
        
        for root, _, files, _ in safe_walk(repo_local_path):
            if set(os.path.relpath(root, repo_local_path).split(os.sep)) & {"node_modules", "venv", ".venv", ".git"}:
                continue
            for file in files:
                if not file.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rs", ".html", ".css")):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_local_path).replace("\\", "/")
                try:
                    content = safe_read_text(
                        repo_local_path,
                        rel_path,
                        encoding="utf-8",
                        errors="ignore",
                        max_bytes=1000000
                    )
                    # Simple chunking: 100 lines per chunk
                    lines = content.splitlines()
                    for i in range(0, len(lines), 100):
                        chunk = "\n".join(lines[i:i+100])
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
        # Re-indexing a shorter/deleted file must not retain stale source chunks.
        stale_ids = sorted(set(collection.get(include=[])["ids"]) - set(ids))
        for i in range(0, len(stale_ids), 100):
            collection.delete(ids=stale_ids[i:i+100])
        return {"status": "success", "documents_indexed": len(docs)}
    except Exception as e:
        print(f"Error indexing codebase: {e}")
        return {"status": "error", "documents_indexed": 0}

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
