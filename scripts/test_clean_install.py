import os
import subprocess
import sys

def test_install(requirements_file, env_name):
    print(f"--- Testing Clean Install: {env_name} ---")
    import tempfile
    scratch_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "scratch_venv")
    os.makedirs(scratch_dir, exist_ok=True)
    env_dir = os.path.join(scratch_dir, env_name)
    
    subprocess.run([sys.executable, "-m", "venv", env_dir], check=True)
    
    pip_exe = os.path.join(env_dir, "Scripts", "pip")
    python_exe = os.path.join(env_dir, "Scripts", "python")
    
    print("Installing requirements...")
    res = subprocess.run([pip_exe, "install", "-r", requirements_file], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Install failed:\n{res.stderr}")
        sys.exit(1)
        
    print("Running pip check...")
    res = subprocess.run([pip_exe, "check"], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Pip check failed:\n{res.stdout}\n{res.stderr}")
        sys.exit(1)
    
    print("Testing imports...")
    import_script = """
import langchain
import langchain_core
import langchain_openai
import langchain_groq
import langgraph
import tiktoken
import pydantic
"""
    if "requirements.txt" in requirements_file and "worker" not in requirements_file:
        import_script += "\nimport fastapi\nimport chromadb\n"
        
    res = subprocess.run([python_exe, "-c", import_script], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Imports failed:\n{res.stderr}")
        sys.exit(1)
        
    print(f"Success: {env_name}!\n")

if __name__ == "__main__":
    test_install("backend/requirements.txt", "venv_backend")
    test_install("backend/requirements-worker.txt", "venv_worker")
