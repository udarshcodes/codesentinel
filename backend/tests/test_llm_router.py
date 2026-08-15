import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.llm_router import invoke_llm, count_tokens
import tools.key_dispatcher

class TestLLMRouter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tools.key_dispatcher._state["skipped"] = set()
        tools.key_dispatcher._state["emergency_active"] = False
        
    @patch("tools.key_dispatcher.GROQ_API_KEYS", ["fake_key"])
    @patch("tools.llm_router.GROQ_API_KEYS", ["fake_key"])
    @patch("tools.llm_router.ChatGroq")
    async def test_invoke_llm_json_parsing(self, mock_chat_groq):
        # Setup mock to return a valid JSON string
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '```json\n{"status": "success", "id": 1}\n```'
        mock_response.usage_metadata = {"total_tokens": 100, "output_tokens": 20}
        mock_instance.invoke.return_value = mock_response
        mock_chat_groq.return_value.bind.return_value = mock_instance

        result = await invoke_llm("Analyze this", "bug_investigator", expect_json=True)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["id"], 1)

    @patch("tools.key_dispatcher.GROQ_API_KEYS", ["fake_key"])
    @patch("tools.llm_router.GROQ_API_KEYS", ["fake_key"])
    @patch("tools.llm_router.ChatGroq")
    async def test_invoke_llm_tier_escalation(self, mock_chat_groq):
        # Setup mock to fail JSON parsing on first try (Tier 1), 
        # then fail again, forcing escalation to Tier 2
        mock_instance = MagicMock()
        mock_response_bad = MagicMock()
        mock_response_bad.content = 'This is not JSON at all'
        mock_response_bad.usage_metadata = {"total_tokens": 10, "output_tokens": 5}
    
        mock_response_good = MagicMock()
        mock_response_good.content = '{"escalated": true}'
        mock_response_good.usage_metadata = {"total_tokens": 10, "output_tokens": 5}
        
        # Returns bad response twice (exhausting Tier 1 retries), then good response (Tier 2)
        mock_instance.invoke.side_effect = [mock_response_bad, mock_response_bad, mock_response_good]
        mock_chat_groq.return_value.bind.return_value = mock_instance

        # Call with expect_json=True
        result = await invoke_llm("Fail twice then succeed", "validator", expect_json=True)
        
        # Verify it eventually succeeded via escalation
        self.assertTrue(result.get("escalated"))
        # Verify it was called 3 times total
        self.assertEqual(mock_instance.invoke.call_count, 3)

    @patch("tools.key_dispatcher.GROQ_API_KEYS", ["fake_key"])
    @patch("tools.llm_router.GROQ_API_KEYS", ["fake_key"])
    @patch("tools.llm_router.ChatGroq")
    async def test_invoke_llm_token_truncation(self, mock_chat_groq):
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"result": "truncated"}'
        mock_instance.invoke.return_value = mock_response
        mock_chat_groq.return_value.bind.return_value = mock_instance

        # Create a prompt that exceeds the validator budget (3000 prompt tokens)
        # 1 word ~ 1.3 tokens. Let's make a massive prompt.
        massive_prompt = "word " * 4000 
        self.assertGreater(count_tokens(massive_prompt), 3000)

        await invoke_llm(massive_prompt, "validator", expect_json=True)
        
        # The prompt actually sent to the LLM should be truncated
        actual_prompt_sent = mock_instance.invoke.call_args[0][0]
        self.assertIn("[FILE TRUNCATED DUE TO TOKEN LIMIT]", actual_prompt_sent)
        self.assertLess(len(actual_prompt_sent), len(massive_prompt))

if __name__ == "__main__":
    unittest.main()
