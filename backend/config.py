import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TEMP_REPO_PATH = os.getenv("TEMP_REPO_PATH", "/tmp/repos")