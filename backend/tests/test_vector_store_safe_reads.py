import ast
import os
import shutil
import sys
import tempfile
import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")

import threading
import time

from tools.vector_store import index_codebase, query_codebase


def test_vector_store_no_unsafe_reads():
    file_path = os.path.join(
        os.path.dirname(__file__), "..", "tools", "vector_store.py"
    )
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source, filename="vector_store.py")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and func.value.id == "os" and func.attr == "walk":
                    pytest.fail(f"Found unsafe os.walk() at line {node.lineno}")
            elif isinstance(func, ast.Name):
                if func.id == "open":
                    pytest.fail(f"Found unsafe open() at line {node.lineno}")


def test_vector_store_rag_contamination():
    repo_dir = tempfile.mkdtemp()
    host_dir = tempfile.mkdtemp()
    try:
        canary_path = os.path.join(host_dir, "host_canary.txt")
        with open(canary_path, "w") as f:
            f.write("SUPER_SECRET_CANARY_CONTENT")

        with open(os.path.join(repo_dir, "normal.py"), "w") as f:
            f.write("print('Normal legitimate code')")

        os.symlink(canary_path, os.path.join(repo_dir, "evil.py"))

        repo_url = "https://github.com/test/rag-contamination"
        index_codebase(repo_url, repo_dir)

        # Check normal file is indexed
        normal_res = query_codebase(repo_url, "legitimate")
        assert len(normal_res) > 0, "Normal code should be indexed"

        # Check canary is NOT indexed
        canary_res = query_codebase(repo_url, "SUPER_SECRET_CANARY")
        leaked = any("SUPER_SECRET_CANARY" in res.get("content", "") for res in canary_res)
        assert not leaked, "Canary content leaked into vector store!"

    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)
        shutil.rmtree(host_dir, ignore_errors=True)


def test_vector_store_symlink_chain():
    repo_dir = tempfile.mkdtemp()
    host_dir = tempfile.mkdtemp()
    try:
        canary_path = os.path.join(host_dir, "host_canary.txt")
        with open(canary_path, "w") as f:
            f.write("CHAIN_SECRET_CONTENT")

        # c -> host_canary
        os.symlink(canary_path, os.path.join(repo_dir, "c.py"))
        # b -> c
        os.symlink(os.path.join(repo_dir, "c.py"), os.path.join(repo_dir, "b.py"))
        # a -> b
        os.symlink(os.path.join(repo_dir, "b.py"), os.path.join(repo_dir, "a.py"))

        repo_url = "https://github.com/test/rag-symlink-chain"
        index_codebase(repo_url, repo_dir)

        canary_res = query_codebase(repo_url, "CHAIN_SECRET")
        leaked = any("CHAIN_SECRET" in res.get("content", "") for res in canary_res)
        assert not leaked, "Symlink chain leaked canary content!"

    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)
        shutil.rmtree(host_dir, ignore_errors=True)


def test_vector_store_concurrent_replacement():
    repo_dir = tempfile.mkdtemp()
    host_dir = tempfile.mkdtemp()
    try:
        canary_path = os.path.join(host_dir, "host_canary.txt")
        with open(canary_path, "w") as f:
            f.write("RACE_SECRET_CONTENT")

        target_path = os.path.join(repo_dir, "target.py")

        # Start race condition thread
        stop_race = False

        def racer():
            while not stop_race:
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    with open(target_path, "w") as f:
                        f.write("legitimate content")
                    
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    os.symlink(canary_path, target_path)
                except Exception:
                    pass

        t = threading.Thread(target=racer)
        t.start()

        repo_url = "https://github.com/test/rag-race"
        
        # Run indexing a few times while the race condition is active
        for i in range(10):
            index_codebase(repo_url, repo_dir)
            
        stop_race = True
        t.join()

        canary_res = query_codebase(repo_url, "RACE_SECRET")
        leaked = any("RACE_SECRET" in res.get("content", "") for res in canary_res)
        assert not leaked, "TOCTOU concurrent replacement attack succeeded!"
        
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)
        shutil.rmtree(host_dir, ignore_errors=True)
