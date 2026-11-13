import os
import tempfile
import pytest
import shutil

temp_dir = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = os.path.join(temp_dir.name, "test_codesentinel.db")
os.environ["TESTING"] = "1"

# Create a session-scoped temp dir for Chroma, override env variable
chroma_temp_dir = tempfile.TemporaryDirectory()
os.environ["CHROMA_PERSIST_PATH"] = chroma_temp_dir.name

os.environ["TASK_ID"] = "test_task"
os.environ["REPO_URL"] = "test"
os.environ["BACKEND_URL"] = "test_backend"
os.environ["WORKER_ATTEMPT_ID"] = "test_attempt"

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

@pytest.fixture(autouse=True, scope="session")
def use_temp_db():
    yield
    try:
        from tools.vector_store import close_vector_store
        close_vector_store()
        # Tests also create direct clients, outside vector_store's singleton.
        from chromadb.api.client import SharedSystemClient
        for system in list(SharedSystemClient._identifier_to_system.values()):
            system.stop()
        SharedSystemClient.clear_system_cache()
        temp_dir.cleanup()
        chroma_temp_dir.cleanup()
    except Exception:
        pass

@pytest.fixture(autouse=True)
def isolate_chroma(monkeypatch):
    """Ensure vector_store client and fixes_collection are reset between tests."""
    try:
        import tools.vector_store
        monkeypatch.setattr(tools.vector_store, "client", None)
        monkeypatch.setattr(tools.vector_store, "fixes_collection", None)
        monkeypatch.setattr(tools.vector_store, "CHROMA_PERSIST_PATH", chroma_temp_dir.name)
    except ImportError:
        yield
        return
    yield
    tools.vector_store.close_vector_store()

def pytest_runtest_teardown(item, nextitem):
    # Ensure test isolation by restoring the working directory using an absolute path.
    # This prevents pytest from being stranded in deleted temporary directories.
    try:
        os.chdir(PROJECT_ROOT)
    except Exception:
        pass
