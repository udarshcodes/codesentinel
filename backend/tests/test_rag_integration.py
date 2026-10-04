import os
import sys
import unittest
import tempfile
import shutil
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.vector_store import (
    store_validated_fix,
    query_similar_fixes,
    index_codebase,
    query_codebase
)
from agents.bug_investigator import agent_bug_investigator
from models.pipeline_state import PipelineState

# Mock the invoke_llm to avoid real API calls but capture the prompt
mocked_prompt = ""
async def mock_invoke_llm(prompt, agent_name, task_class=None, expect_json=False, **kwargs):
    global mocked_prompt
    mocked_prompt = prompt
    return {
        "id": 1,
        "description": "Mocked issue description",
        "root_cause": "Mocked root cause",
        "severity": "high",
        "impact": "high",
        "affected_files": ["auth.py"]
    }

import agents.bug_investigator
agents.bug_investigator.invoke_llm = mock_invoke_llm

class TestRAGIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        import tools.vector_store
        tools.vector_store.CHROMA_PERSIST_PATH = self.temp_dir
        tools.vector_store.client = None
        tools.vector_store.fixes_collection = None
        global mocked_prompt
        mocked_prompt = ""

    def tearDown(self):
        import tools.vector_store
        tools.vector_store.client = None
        tools.vector_store.fixes_collection = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_rag_loop(self):
        repo_url = "https://github.com/integration/test-repo"
        repo_dir = os.path.join(self.temp_dir, "fake_repo")
        os.makedirs(repo_dir)

        # 1. Create a small temporary repository with realistic vulnerable code
        vuln_code = """
def authenticate_user(username, password):
    # SQL Injection vulnerability
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    db.execute(query)
"""
        with open(os.path.join(repo_dir, "auth.py"), "w") as f:
            f.write(vuln_code)

        # 2. Index it
        status = index_codebase(repo_url, repo_dir)
        self.assertEqual(status["status"], "success")
        self.assertGreater(status["documents_indexed"], 0)

        # 3. Query for a concept related to that vulnerability
        code_results = query_codebase(repo_url, "SQL Injection in authenticate_user")
        
        # 4. Assert relevant file retrieved
        self.assertGreater(len(code_results), 0)
        self.assertEqual(code_results[0]["file"], "auth.py")

        # 5. Create a validated fix record
        issue_desc = "SQL Injection in authenticate_user"
        patch_code = "query = 'SELECT * FROM users WHERE username = ? AND password = ?'"
        store_validated_fix(repo_url, issue_desc, patch_code, 0.99)

        # 6. Query similar fixes
        fix_results = query_similar_fixes(repo_url, "SQL injection in auth")
        
        # 7. Assert that validated fix is retrieved
        self.assertGreater(len(fix_results), 0)
        self.assertEqual(fix_results[0]["patch"], patch_code)

        # 8. Pass retrieved context into Bug Investigator
        state: PipelineState = {
            "repo_url": repo_url,
            "repo_local_path": repo_dir,
            "static_findings": [{"issue": issue_desc, "file": "auth.py"}],
            "dependency_findings": [],
            "rag_status": status
        }
        
        # We need GROQ_API_KEYS set to truthy to enter the logic
        import agents.bug_investigator
        agents.bug_investigator.GROQ_API_KEYS = ["fake-key"]
        
        # Run agent_bug_investigator
        result = asyncio.run(agent_bug_investigator(state))

        # 9. Verify prompt contains retrieved codebase context
        self.assertIn("Semantic Codebase Context", mocked_prompt)
        self.assertIn("auth.py", mocked_prompt)
        self.assertIn("SELECT * FROM users", mocked_prompt)

        # 10. Verify prompt contains historical fix context
        self.assertIn("Similar Past Fixes from Knowledge Base", mocked_prompt)
        self.assertIn(patch_code, mocked_prompt)

    def test_rag_lifecycle_deterministic(self):
        from tools import context_cache
        import asyncio
        repo_url = "https://github.com/integration/deterministic"
        
        async def run_test():
            async def dummy_index():
                await asyncio.sleep(0.1)
                return {"status": "success", "documents_indexed": 42}
                
            rag_task = asyncio.create_task(dummy_index())
            context_cache.store(repo_url, "rag_task", rag_task)
            
            state = {
                "repo_url": repo_url,
                "repo_local_path": "/tmp/dummy",
                "static_findings": [{"issue": "dummy", "file": "dummy.py"}],
                "dependency_findings": []
            }
            
            import agents.bug_investigator
            agents.bug_investigator.GROQ_API_KEYS = ["fake-key"]
            
            await agents.bug_investigator.agent_bug_investigator(state)
            self.assertEqual(state.get("rag_status", {}).get("documents_indexed"), 42)
            
        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
