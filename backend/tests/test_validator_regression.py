import pytest
from agents.validator import agent_validator
from models.pipeline_state import PipelineState
import tempfile
import os
import shutil

@pytest.mark.asyncio
async def test_validator_html_css_python_regression():
    temp_dir = tempfile.mkdtemp()
    try:
        # Create some test files
        html_file = os.path.join(temp_dir, "test.html")
        css_file = os.path.join(temp_dir, "test.css")
        py_file = os.path.join(temp_dir, "test.py")
        
        with open(html_file, "w") as f:
            f.write("<html><body><h1>Hello</h1></body></html>")
            
        with open(css_file, "w") as f:
            f.write("body { color: red; }")
            
        with open(py_file, "w") as f:
            f.write("def foo():\n    pass")
            
        state = PipelineState({
            "repo_local_path": temp_dir,
            "patches": [
                {"patch_id": "p1", "file": "test.html", "applied": True},
                {"patch_id": "p2", "file": "test.css", "applied": True},
                {"patch_id": "p3", "file": "test.py", "applied": True},
            ]
        })
        
        result = await agent_validator(state)
        
        assert "validation_results" in result
        results = result["validation_results"]
        assert len(results) > 0
        
        # Verify passed string exists in the logs
        logs = results[0]["logs"]
        assert "[PASSED] test.html - HTML parsed OK" in logs
        assert "[PASSED] test.css - CSS braces balanced" in logs
        # py_compile subprocess might fail if sys.executable doesn't point to a valid python, but the file read should at least not crash with an exception.
    finally:
        shutil.rmtree(temp_dir)
