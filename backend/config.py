import os
import tempfile
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_raw_keys = os.getenv("GROQ_API_KEY", "")
_comma_keys = [k.strip() for k in _raw_keys.split(",") if k.strip()]
_env_keys = [os.getenv(f"GROQ_API_KEY_{i}", "").strip() for i in range(1, 7)]
_env_keys = [k for k in _env_keys if k]
GROQ_API_KEYS: list[str] = _comma_keys if _comma_keys else _env_keys

# Backwards compatible single key accessor
GROQ_API_KEY: str = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""
GROQ_EMERGENCY_KEY: str = os.getenv("GROQ_EMERGENCY_KEY", "")

# Per key daily token budget
_tokens_env = os.getenv("GROQ_TOKENS_PER_KEY")
GROQ_TOKENS_PER_KEY_PER_DAY = int(_tokens_env) if _tokens_env else 500000
GROQ_TOTAL_DAILY_BUDGET = GROQ_TOKENS_PER_KEY_PER_DAY * len(GROQ_API_KEYS) if GROQ_TOKENS_PER_KEY_PER_DAY else None

# Updated routing configuration
PRIMARY_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
FALLBACK_MODEL = "qwen/qwen3.6-27b"

TEMP_REPO_PATH = os.getenv(
    "TEMP_REPO_PATH", os.path.join(tempfile.gettempdir(), "repos")
)

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
}
