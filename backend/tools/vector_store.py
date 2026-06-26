import os
import hashlib
import chromadb

CHROMA_PERSIST_PATH = os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")
client = None
fixes_collection = None


def _get_collections():
    global client, fixes_collection
    if client is None:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)
        fixes_collection = client.get_or_create_collection("validated_fixes")
    return fixes_collection


def store_validated_fix(issue_description: str, patch: str, confidence: float):
    """Called by Validator after a fix passes. Stores embedding of the fix."""
    try:
        fixes = _get_collections()
        doc_id = f"fix_{hashlib.sha256((issue_description + patch).encode()).hexdigest()[:16]}"
        fixes.upsert(
            documents=[issue_description],
            metadatas=[{"patch": patch, "confidence": confidence}],
            ids=[doc_id],
        )
    except Exception as e:
        print(f"Error storing validated fix: {e}")


def query_similar_fixes(issue_description: str, n_results: int = 3) -> list:
    """Called by Bug Investigator before LLM call to retrieve past fix context."""
    try:
        fixes = _get_collections()
        results = fixes.query(query_texts=[issue_description], n_results=n_results)
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
