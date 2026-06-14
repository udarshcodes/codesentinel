import os
import chromadb
from chromadb.utils import embedding_functions

CHROMA_PERSIST_PATH = os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")
client = chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)

# Existing collection for repo chunks (stubbed for compatibility)
repo_collection = client.get_or_create_collection('repo_chunks')

# NEW — collection for past successful fixes
fixes_collection = client.get_or_create_collection('validated_fixes')

def store_validated_fix(issue_description: str, patch: str, confidence: float):
    '''Called by Validator after a fix passes. Stores embedding of the fix.'''
    try:
        doc_id = f'fix_{hash(issue_description + patch)}'
        fixes_collection.add(
            documents=[issue_description],
            metadatas=[{'patch': patch, 'confidence': confidence}],
            ids=[doc_id]
        )
    except Exception as e:
        print(f"Error storing validated fix: {e}")

def query_similar_fixes(issue_description: str, n_results: int = 3) -> list:
    '''Called by Bug Investigator before LLM call to retrieve past fix context.'''
    try:
        results = fixes_collection.query(
            query_texts=[issue_description],
            n_results=n_results
        )
        fixes = []
        if not results.get('documents') or not results['documents'][0]:
            return fixes
            
        for i, doc in enumerate(results['documents'][0]):
            meta = results['metadatas'][0][i]
            fixes.append({'issue': doc, 'patch': meta['patch'], 'confidence': meta['confidence']})
        return fixes
    except Exception as e:
        print(f"Error querying similar fixes: {e}")
        return []
