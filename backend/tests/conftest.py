import os
import tempfile
import pytest

temp_dir = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = os.path.join(temp_dir.name, "test_codesentinel.db")
os.environ["TESTING"] = "1"


@pytest.fixture(autouse=True, scope="session")
def use_temp_db():
    yield
    temp_dir.cleanup()
