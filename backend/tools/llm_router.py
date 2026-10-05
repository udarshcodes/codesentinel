"""
LLM Router — Deterministic model tiering, pre-flight tokenization,
per-agent token budgets, retry/fallback logic, and telemetry.
"""

import json
import asyncio
import tiktoken
from langchain_groq import ChatGroq
from config import GROQ_API_KEYS, PRIMARY_MODELS, FALLBACK_MODEL
from tools.key_dispatcher import get_next_key, record_usage, mark_rate_limited
from tools.response_cache import get_cached, set_cached

AGENT_BUDGETS = {
    "repo_mapper": {"prompt": 4000, "completion": 1000},
    "bug_investigator": {"prompt": 6000, "completion": 2000},
    "repair_planner": {"prompt": 4000, "completion": 2000},
    "code_generator": {"prompt": 6000, "completion": 2500},
    "validator": {"prompt": 3000, "completion": 1000},
    "security_verifier": {"prompt": 3000, "completion": 1000},
    "pr_author": {"prompt": 4000, "completion": 1000},
}

# Maximum schema-validation retries per tier before escalating / aborting.
MAX_RETRIES_PER_TIER = 3
ESCALATION_TOKEN_THRESHOLD = 5000

class LLMExhaustionError(Exception):
    def __init__(self, status: str, model: str, reset_time: float, last_error: str):
        self.status = status
        self.model = model
        self.reset_time = reset_time
        self.last_error = last_error
        super().__init__(f"LLM Exhaustion on {model}: {last_error}")

_ENCODING = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    """Return an approximate token count using the offline tokenizer."""
    return len(_ENCODING.encode(text))


_telemetry: dict[str, dict] = {}


def get_telemetry() -> dict:
    """Return a copy of the current telemetry data."""
    return dict(_telemetry)


def _record(
    agent_name: str, prompt_tokens: int, completion_tokens: int, model_used: str
):
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
        f"req: {prompt_tokens}/{entry['prompt_budget']} prompt, "
        f"{completion_tokens}/{entry['completion_budget']} comp | "
        f"session: {entry['prompt_tokens']} prompt, {entry['completion_tokens']} comp | "
        f"model={model_used}"
    )


async def invoke_llm(
    prompt: str,
    agent_name: str,
    *,
    task_class: str = None,
    expect_json: bool = True,
    json_array: bool = False,
) -> str | dict | list:
    """
    Central LLM invocation with deterministic tiering, budgets, and retries.
    """
    if not GROQ_API_KEYS:
        raise RuntimeError("GROQ_API_KEYS is not configured.")

    prompt_tokens = count_tokens(prompt)
    budget = AGENT_BUDGETS.get(agent_name, {"prompt": 6000, "completion": 2000})

    if prompt_tokens > budget["prompt"]:
        print(
            f"[LLMRouter] WARNING: {agent_name} prompt ({prompt_tokens} tokens) "
            f"exceeds budget ({budget['prompt']}). Truncating end."
        )
        max_chars = budget["prompt"] * 4
        prompt = prompt[:max_chars] + "\n```\n[FILE TRUNCATED DUE TO TOKEN LIMIT]\n"
        prompt_tokens = count_tokens(prompt)

    models_to_try = []
    # Route by explicit task_class if provided, otherwise default to token-based heuristic.
    # We map LIGHT to Tier 1 and DEEP to Tier 2 logic.
    is_tier_1 = False
    if task_class == "LIGHT":
        is_tier_1 = True
    elif task_class == "DEEP":
        is_tier_1 = False
    elif prompt_tokens <= ESCALATION_TOKEN_THRESHOLD:
        is_tier_1 = True

    if is_tier_1:
        models_to_try.append(PRIMARY_MODELS[0])
        models_to_try.append(PRIMARY_MODELS[1])
    else:
        models_to_try.append(PRIMARY_MODELS[1])
    
    models_to_try.append(FALLBACK_MODEL)
    
    last_error_str = "max_retries_exceeded"
    
    for current_model in models_to_try:
        cached_response = get_cached(prompt, current_model)
        if cached_response:
            print(f"[LLMRouter] Cache hit for {current_model}. Skipping API call.")
            return _parse_cache_or_raw(cached_response, expect_json, json_array, agent_name, prompt_tokens, current_model, prompt)
            
        for attempt in range(1, MAX_RETRIES_PER_TIER + 1):
            success = False
            raw = ""
            completion_tokens = 0
            parsed_json = None
            
            # Try available keys
            api_key = None
            key_idx = None
            for key_rotation in range(len(GROQ_API_KEYS) + 1):
                try:
                    api_key, key_idx = get_next_key()
                except RuntimeError as e:
                    if "DATABASE_URL" in str(e):
                        raise  # Do not swallow configuration errors as LLM exhaustion
                    # All keys including emergency are exhausted
                    raise LLMExhaustionError(
                        status="WAITING_FOR_LLM_CAPACITY", 
                        model=current_model, 
                        reset_time=300.0, 
                        last_error=str(e)
                    )
                
                llm = ChatGroq(
                    model=current_model,
                    api_key=api_key,
                    max_tokens=budget["completion"],
                )
                # Retry without strict json mode if it failed validation on the API side
                use_strict_json = expect_json and not json_array and "json_validate_failed" not in last_error_str
                if use_strict_json:
                    llm = llm.bind(response_format={"type": "json_object"})

                try:
                    res = await asyncio.to_thread(llm.invoke, prompt)
                    raw = res.content.strip()
                    usage = getattr(res, "usage_metadata", {}) or {}
                    total_tokens = usage.get("total_tokens", 0)
                    if total_tokens:
                        record_usage(key_idx, total_tokens)

                    completion_tokens = usage.get("output_tokens", 0)
                    if not completion_tokens:
                        completion_tokens = count_tokens(raw)
                    
                    if expect_json:
                        cleaned = raw.replace("```json", "").replace("```", "").strip()
                        open_char = "[" if json_array else "{"
                        close_char = "]" if json_array else "}"
                        start_idx = cleaned.find(open_char)
                        if start_idx == -1:
                            raise ValueError("No JSON block found in response")
                        depth = 0
                        end_idx = -1
                        for i in range(start_idx, len(cleaned)):
                            if cleaned[i] == open_char:
                                depth += 1
                            elif cleaned[i] == close_char:
                                depth -= 1
                                if depth == 0:
                                    end_idx = i
                                    break
                        if end_idx == -1:
                            raise ValueError("Mismatched braces/brackets in JSON response")
                        json_str = cleaned[start_idx : end_idx + 1]
                        parsed_json = json.loads(json_str)
                    
                    success = True
                    break # Success! Break out of key rotation
                
                except Exception as e:
                    err_str = str(e).lower()
                    last_error_str = err_str
                    if "rate limit" in err_str or "429" in err_str:
                        mark_rate_limited(key_idx)
                        if key_idx == -1:
                            print("[LLMRouter] Emergency key also rate limited.")
                        continue # Try next key
                    else:
                        print(f"[LLMRouter] {agent_name} attempt {attempt} failed (model={current_model}): {e}")
                        break # Not a rate limit, break key loop and increment attempt
            
            if success:
                _record(agent_name, prompt_tokens, completion_tokens, current_model)
                set_cached(prompt, current_model, raw)
                if expect_json:
                    return parsed_json
                return raw
                
        # If we exhausted attempts for this model, we move to the next model in models_to_try
        print(f"[LLMRouter] Exhausted {MAX_RETRIES_PER_TIER} attempts for model {current_model}. Moving to next.")

    # All models exhausted
    raise LLMExhaustionError(
        status="WAITING_FOR_LLM_CAPACITY", 
        model=current_model if 'current_model' in locals() else "unknown", 
        reset_time=300.0, 
        last_error=last_error_str
    )

def _parse_cache_or_raw(raw: str, expect_json: bool, json_array: bool, agent_name: str, prompt_tokens: int, current_model: str, prompt: str):
    _record(agent_name, prompt_tokens, 0, current_model)
    if not expect_json:
        return raw
    try:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        if json_array:
            start_idx = cleaned.find("[")
            end_idx = cleaned.rfind("]")
        else:
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")

        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            raise ValueError(f"No JSON found in response: {cleaned[:200]}")

        json_str = cleaned[start_idx : end_idx + 1]
        return json.loads(json_str)
    except Exception as e:
        print(f"[LLMRouter] {agent_name} JSON parse failed: {e}")
        return {} if not json_array else []
