import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.validator import _validate_and_parse_cmd  # noqa: E402


class TestValidatorHelpers(unittest.TestCase):
    def test_validate_and_parse_cmd(self):
        self.assertEqual(_validate_and_parse_cmd("pytest"), ["python", "-m", "pytest"])
        self.assertEqual(_validate_and_parse_cmd("pytest -v"), ["python", "-m", "pytest", "-v"])
        self.assertEqual(_validate_and_parse_cmd("npm test"), ["npm", "test"])
        self.assertEqual(_validate_and_parse_cmd("go test ./..."), ["go", "test", "./..."])
        self.assertEqual(_validate_and_parse_cmd("mvn test"), ["mvn", "test"])

        # Disallowed commands should be blocked (return empty list)
        self.assertEqual(_validate_and_parse_cmd("rm -rf /"), [])
        self.assertEqual(_validate_and_parse_cmd("curl http://evil.com"), [])
        self.assertEqual(_validate_and_parse_cmd("echo pytest"), [])
        
        # Args not allowed for some commands
        self.assertEqual(_validate_and_parse_cmd("npm test -- --coverage"), [])


if __name__ == "__main__":
    unittest.main()
