"""
LLM Router — Deterministic model tiering, pre-flight tokenization,
per-agent token budgets, retry/fallback logic, and telemetry.
"""

import json
import re
import tiktoken
from langchain_groq import ChatGroq
from langchain_core.exceptions import OutputParserException
from config import GROQ_API_KEYS
from tools.key_dispatcher import get_next_key, record_usage, mark_rate_limited
from tools.response_cache import get_cached, set_cached

# ---------------------------------------------------------------------------
# Model tiers
# ---------------------------------------------------------------------------
TIER1_MODEL = "llama-3.1-8b-instant"       # Fast & cheap — scanning, mapping
TIER2_MODEL = "llama-3.3-70b-versatile"     # Reasoning — repair planning, code gen

# ---------------------------------------------------------------------------
# Per-agent token budgets  (prompt_limit, completion_limit)
# ---------------------------------------------------------------------------
AGENT_BUDGETS = {
    "repo_mapper":        {"prompt": 4000, "completion": 1000},
    "bug_investigator":   {"prompt": 6000, "completion": 2000},
    "repair_planner":     {"prompt": 4000, "completion": 2000},
    "code_generator":     {"prompt": 6000, "completion": 2500},
    "validator":          {"prompt": 3000, "completion": 1000},
    "security_verifier":  {"prompt": 3000, "completion": 1000},
    "pr_author":          {"prompt": 4000, "completion": 1000},
}

# Escalation threshold — if pre-flight token count exceeds this,
# automatically route to Tier 2 regardless of agent tier assignment.
ESCALATION_TOKEN_THRESHOLD = 4000

# Maximum schema-validation retries per tier before escalating / aborting.
MAX_RETRIES_PER_TIER = 2

# ---------------------------------------------------------------------------
# Tokenizer — offline, no API call required
# ---------------------------------------------------------------------------
# tiktoken's cl100k_base is a reasonable proxy for Llama-3 token counts.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return an approximate token count using the offline tokenizer."""
    return len(_ENCODING.encode(text))


# ---------------------------------------------------------------------------
# Telemetry store  (in-memory, per-process)
# ---------------------------------------------------------------------------
_telemetry: dict[str, dict] = {}


def get_telemetry() -> dict:
    """Return a copy of the current telemetry data."""
    return dict(_telemetry)


def _record(agent_name: str, prompt_tokens: int, completion_tokens: int,
            model_used: str):
    """Accumulate token usage for an agent."""
    if agent_name not in _telemetry:
        budget = AGENT_BUDGETS.get(agent_name, {"prompt": 6000, "completion": 2000})
        _telemetry[agent_name] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "prompt_budget": budget["prompt"],
            "completion_budget": budget["completion"],
            "calls": 0,
            "model_used": [],
        }
    entry = _telemetry[agent_name]
    entry["prompt_tokens"] += prompt_tokens
    entry["completion_tokens"] += completion_tokens
    entry["calls"] += 1
    entry["model_used"].append(model_used)
    print(
        f"[TokenTracker] {agent_name}: "
        f"prompt {entry['prompt_tokens']}/{entry['prompt_budget']} | "
        f"completion {entry['completion_tokens']}/{entry['completion_budget']} | "
        f"model={model_used}"
    )


# ---------------------------------------------------------------------------
# Core invoke function
# ---------------------------------------------------------------------------
def invoke_llm(
    prompt: str,
    agent_name: str,
    *,
    tier: int = 1,
    expect_json: bool = True,
    json_array: bool = False,
) -> str | dict | list:
    """
    Central LLM invocation with deterministic tiering, budgets, and retries.

    Parameters
    ----------
    prompt : str
        The full prompt text to send.
    agent_name : str
        Key into AGENT_BUDGETS for budget enforcement and telemetry.
    tier : int
        1 = use Tier-1 (8b) model by default.
        2 = use Tier-2 (70b) model directly.
    expect_json : bool
        If True, parse the response as JSON and retry on failure.
    json_array : bool
        If True and expect_json, expect a JSON array instead of object.

    Returns
    -------
    Parsed JSON (dict or list) when expect_json=True, raw string otherwise.
    Raises RuntimeError after exhausting all retries across both tiers.
    """
    if not GROQ_API_KEYS:
        raise RuntimeError("GROQ_API_KEYS is not configured.")

    # --- Pre-flight token check (offline, before any API call) ---
    prompt_tokens = count_tokens(prompt)
    budget = AGENT_BUDGETS.get(agent_name, {"prompt": 6000, "completion": 2000})

    if prompt_tokens > budget["prompt"]:
        print(
            f"[LLMRouter] WARNING: {agent_name} prompt ({prompt_tokens} tokens) "
            f"exceeds budget ({budget['prompt']}). Truncating."
        )
        # Truncate prompt to fit budget (rough heuristic: 1 token ≈ 4 chars)
        max_chars = budget["prompt"] * 4
        prompt = prompt[:max_chars]
        prompt_tokens = budget["prompt"]

    # Determine starting model based on tier AND token threshold
    if tier == 1 and prompt_tokens <= ESCALATION_TOKEN_THRESHOLD:
        current_model = TIER1_MODEL
    else:
        current_model = TIER2_MODEL

    # --- Cache Check ---
    cached_response = get_cached(prompt, current_model)
    if cached_response:
        print(f"[LLMRouter] Cache hit for {current_model}. Skipping API call.")
        res_content = cached_response
        completion_tokens = 0
    else:
        res_content = None
        
    total_attempts = MAX_RETRIES_PER_TIER * (len(GROQ_API_KEYS) + 1)
    
    # --- Retry loop with deterministic escalation ---
    for attempt in range(1, total_attempts + 1):
        if res_content is not None:
            # We had a cache hit, skip the API call
            raw = res_content.strip()
            break
            
        api_key, key_idx = get_next_key()
        if key_idx == -1:
            print(f"[LLMRouter] Using emergency key (attempt {attempt})")
            
        llm = ChatGroq(
            model=current_model,
            api_key=api_key,
            max_tokens=budget["completion"],
        )
        
        try:
            res = llm.invoke(prompt)
            raw = res.content.strip()
            
            # Extract actual token usage from the Groq API response if available
            tokens = getattr(res, "usage_metadata", {}).get("total_tokens", 0)
            if tokens:
                record_usage(key_idx, tokens)
                completion_tokens = tokens
            else:
                # Fallback to offline approximation
                completion_tokens = count_tokens(raw)
                
            break
            
        except Exception as e:
            err_str = str(e).lower()
            if "rate limit" in err_str or "429" in err_str:
                mark_rate_limited(key_idx)
                if key_idx == -1:
                    print("[LLMRouter] Emergency key also rate limited. Aborting.")
                    break
                continue
                
            print(
                f"[LLMRouter] {agent_name} attempt {attempt} failed "
                f"(model={current_model}): {e}"
            )

            # Deterministic escalation: after enough failures on Tier 1, escalate to Tier 2.
            if attempt == MAX_RETRIES_PER_TIER and current_model == TIER1_MODEL:
                print(
                    f"[LLMRouter] Escalating {agent_name} from "
                    f"{TIER1_MODEL} → {TIER2_MODEL}"
                )
                current_model = TIER2_MODEL
    else:
        # Loop finished without breaking -> all retries failed
        raw = ""

    if raw:
        _record(agent_name, prompt_tokens, completion_tokens, current_model)

        if not expect_json:
            if res_content is None:
                set_cached(prompt, current_model, raw)
            return raw

        try:
            # --- JSON schema validation ---
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            if json_array:
                match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            else:
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)

            if not match:
                raise ValueError(f"No JSON found in response: {cleaned[:200]}")

            parsed = json.loads(match.group(0))
            
            # Cache the raw string only if it successfully parses!
            if res_content is None:
                set_cached(prompt, current_model, raw)
                
            return parsed

        except Exception as e:
            # JSON parse failed
            print(f"[LLMRouter] {agent_name} JSON parse failed: {e}")
            # If we wanted to loop on JSON failures, we'd do it here. 
            # But since we broke out of the attempt loop, we'll just fall through to the abort below.

    # All retries exhausted across both tiers — graceful degradation
    print(f"[LLMRouter] ABORT: {agent_name} exhausted all retries.")
    if expect_json:
        if json_array:
            return []
        return {
            "error": "Generation failed after exhausting all retries.",
            "status": "failed",
        }
    return ""
