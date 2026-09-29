"""Environment-based API key rotation for LiteLLM providers."""
from __future__ import annotations

import os
import re
from collections import defaultdict
from threading import Lock

_INDEXES: dict[str, int] = defaultdict(int)
_LOCK = Lock()


def _provider_prefix(model: str) -> str | None:
    value = model.lower()
    if value.startswith("gemini/") or "gemini" in value:
        return "GEMINI"
    if value.startswith("anthropic/") or "claude" in value:
        return "ANTHROPIC"
    if value.startswith("openai/") or value.startswith("gpt-"):
        return "OPENAI"
    if value.startswith("huggingface/") or value.startswith("hf/"):
        return "HF"
    return None


def api_keys_for_model(model: str) -> list[str]:
    prefix = _provider_prefix(model)
    if not prefix:
        return []
    values: list[str] = []
    names = [f"{prefix}_API_KEYS", f"{prefix}_API_KEY"]
    if prefix == "HF":
        names.extend(("HF_TOKENS", "HF_TOKEN"))
    for name in names:
        values.extend(value.strip() for value in os.getenv(name, "").split(",") if value.strip())
    numbered = re.compile(rf"^{re.escape(prefix)}_API_KEY_(\d+)$")
    numbered_values = []
    for name, value in os.environ.items():
        match = numbered.match(name)
        if match and value.strip():
            numbered_values.append((int(match.group(1)), value.strip()))
    values.extend(value for _, value in sorted(numbered_values))
    return list(dict.fromkeys(values))


def next_api_key(model: str) -> str | None:
    keys = api_keys_for_model(model)
    if not keys:
        return None
    with _LOCK:
        index = _INDEXES[model] % len(keys)
        _INDEXES[model] += 1
    return keys[index]


def looks_like_key_or_rate_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in (
        "429", "rate limit", "ratelimit", "quota", "resource_exhausted",
        "invalid api key", "invalid_api_key", "unauthorized", "401", "403",
    ))


def is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in (
        "429", "rate limit", "ratelimit", "quota", "resource_exhausted",
    ))
