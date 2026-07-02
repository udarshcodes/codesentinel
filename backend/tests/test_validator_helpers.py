import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.validator import _is_allowed_cmd  # noqa: E402


class TestValidatorHelpers(unittest.TestCase):
    def test_is_allowed_cmd(self):
        self.assertTrue(_is_allowed_cmd("pytest"))
        self.assertTrue(_is_allowed_cmd("pytest -v"))
        self.assertTrue(_is_allowed_cmd("npm test -- --coverage"))
        self.assertTrue(_is_allowed_cmd("go test ./..."))
        self.assertTrue(_is_allowed_cmd("mvn test -Dtest=MyTest"))

        # Disallowed commands should be blocked
        self.assertFalse(_is_allowed_cmd("rm -rf /"))
        self.assertFalse(_is_allowed_cmd("curl http://evil.com"))
        self.assertFalse(_is_allowed_cmd("echo pytest"))


if __name__ == "__main__":
    unittest.main()
