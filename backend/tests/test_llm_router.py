import os
import sys
import unittest
from unittest.mock import patch

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.key_dispatcher import get_next_key


class TestLLMRouter(unittest.TestCase):
    @patch("tools.key_dispatcher.GROQ_API_KEYS", ["key1", "key2"])
    def test_select_api_key(self):
        key1, idx = get_next_key()
        self.assertIn(key1, ["key1", "key2"])

    @patch("tools.key_dispatcher.GROQ_API_KEYS", [])
    @patch("tools.key_dispatcher.GROQ_EMERGENCY_KEY", None)
    def test_select_api_key_empty(self):
        with self.assertRaises(RuntimeError):
            get_next_key()


if __name__ == "__main__":
    unittest.main()
