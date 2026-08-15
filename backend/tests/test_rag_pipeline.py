import os
import sys
import unittest
import tempfile
import shutil

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.vector_store import (
    store_validated_fix,
    query_similar_fixes,
    index_codebase,
    query_codebase
)

class TestRAGPipeline(unittest.TestCase):
    def setUp(self):
        # Override the persist path to a temporary directory for tests
        self.temp_dir = tempfile.mkdtemp()
        import tools.vector_store
        tools.vector_store.CHROMA_PERSIST_PATH = self.temp_dir
        # Reset the client to force a fresh connection to the temp dir
        tools.vector_store.client = None
        tools.vector_store.fixes_collection = None

    def tearDown(self):
        # Clean up the vector store connection
        import tools.vector_store
        tools.vector_store.client = None
        tools.vector_store.fixes_collection = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_past_fixes_rag_isolation(self):
        repo_a = "https://github.com/a/repo-a"
        repo_b = "https://github.com/b/repo-b"

        # Ingest: Store fixes for both repos
        store_validated_fix(repo_a, "Null pointer exception in Auth", "patch A", 0.9)
        store_validated_fix(repo_b, "Null pointer exception in DB", "patch B", 0.9)

        # Retrieve: Query for repo_a
        results_a = query_similar_fixes(repo_a, "Null pointer")
        self.assertEqual(len(results_a), 1)
        self.assertEqual(results_a[0]["patch"], "patch A")

        # Retrieve: Query for repo_b
        results_b = query_similar_fixes(repo_b, "Null pointer")
        self.assertEqual(len(results_b), 1)
        self.assertEqual(results_b[0]["patch"], "patch B")

        # Prove isolation: Query for repo_c (which has no fixes)
        results_c = query_similar_fixes("https://github.com/c/repo-c", "Null pointer")
        self.assertEqual(len(results_c), 0)

    def test_codebase_rag_ingestion(self):
        repo_url = "https://github.com/test/repo"
        repo_dir = os.path.join(self.temp_dir, "fake_repo")
        os.makedirs(repo_dir)

        # Create some fake code files
        with open(os.path.join(repo_dir, "auth.py"), "w") as f:
            f.write("def login(user, pw):\n    return check_password(user, pw)\n")

        with open(os.path.join(repo_dir, "db.py"), "w") as f:
            f.write("def connect():\n    return db.connect('postgres://...')\n")

        # Ingest Codebase
        index_codebase(repo_url, repo_dir)

        # Retrieve Codebase Snippets
        results = query_codebase(repo_url, "How does authentication work?")
        self.assertTrue(len(results) > 0)
        # Should return auth.py snippet because it's semantically closer
        self.assertEqual(results[0]["file"], "auth.py")
        self.assertIn("def login", results[0]["content"])

        # Isolation Check: Query a different repo for the same concept
        results_other = query_codebase("https://github.com/other/repo", "How does authentication work?")
        self.assertEqual(len(results_other), 0)

if __name__ == "__main__":
    unittest.main()
