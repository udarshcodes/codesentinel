import os
from dotenv import load_dotenv

load_dotenv()

_raw_keys = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS: list[str] = [k.strip() for k in _raw_keys.split(",") if k.strip()]

# Backwards compatible single key accessor
GROQ_API_KEY: str = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

# 6th key loaded separately — never enters round robin, only activates on full pool failure
GROQ_EMERGENCY_KEY: str | None = os.getenv("GROQ_EMERGENCY_KEY", "").strip() or None

# Per key daily token budget (Groq free tier: 100k tokens/day per key)
GROQ_TOKENS_PER_KEY_PER_DAY = int(os.getenv("GROQ_TOKENS_PER_KEY", "100000"))
GROQ_TOTAL_DAILY_BUDGET = GROQ_TOKENS_PER_KEY_PER_DAY * len(GROQ_API_KEYS)

TEMP_REPO_PATH = os.getenv("TEMP_REPO_PATH", "/tmp/repos")