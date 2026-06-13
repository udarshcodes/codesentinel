import os
import chromadb
from langchain_huggingface import HuggingFaceEmbeddings

CHROMA_PERSIST_PATH = os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")
client = chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)
collection = client.get_or_create_collection(name="past_fixes")

def get_embeddings():
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def query_past_fixes(issue_description: str, top_k: int = 3):
    embedder = get_embeddings()
    
    try:
        query_embedding = embedder.embed_query(issue_description)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        if not results['documents'] or not results['documents'][0]:
            return []
        return results['documents'][0]
    except Exception as e:
        print(f"Error querying ChromaDB: {e}")
        return []

def store_fix(issue_description: str, fix_details: str):
    embedder = get_embeddings()
    if not embedder:
        return
        
    try:
        doc_id = str(hash(issue_description + fix_details))
        embedding = embedder.embed_query(issue_description)
        
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[fix_details],
            metadatas=[{"issue": issue_description}]
        )
    except Exception as e:
        print(f"Error storing in ChromaDB: {e}")
