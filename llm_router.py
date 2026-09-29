"""Shared LiteLLM Router with key rotation, cooldowns, and model fallback."""
from __future__ import annotations

import time
from threading import Lock
from typing import Any

from api_key_pool import api_keys_for_model, is_rate_limit_error, looks_like_key_or_rate_error

_ROUTERS: dict[tuple[str, str, tuple[str, ...]], Any] = {}
_LOCK = Lock()
FALLBACKS = ["gemini/gemini-3.6-flash", "gemini/gemini-2.5-flash"]


def _router_for(model: str, api_base: str | None = None) -> Any:
    keys = tuple(api_keys_for_model(model))
    cache_key = (model, api_base or "", keys)
    with _LOCK:
        if cache_key in _ROUTERS:
            return _ROUTERS[cache_key]

        from litellm import Router

        deployment_models = [model]
        if model.startswith("gemini/"):
            deployment_models.extend(FALLBACKS)
        deployment_models = list(dict.fromkeys(deployment_models))
        model_list = []
        for deployment_model in deployment_models:
            deployment_keys = keys if deployment_model == model else tuple(api_keys_for_model(deployment_model))
            if not deployment_keys:
                deployment_keys = (None,)
            for api_key in deployment_keys:
                params: dict[str, Any] = {"model": deployment_model}
                if api_key:
                    params["api_key"] = api_key
                if api_base:
                    params["api_base"] = api_base
                model_list.append({"model_name": deployment_model, "litellm_params": params})

        router = Router(
            model_list=model_list,
            num_retries=max(1, len(keys)),
            cooldown_time=60,
            default_fallbacks=FALLBACKS if model.startswith("gemini/") else [],
            max_fallbacks=len(FALLBACKS),
            routing_strategy="simple-shuffle",
        )
        _ROUTERS[cache_key] = router
        return router


def safe_completion(
    model: str,
    messages: list[dict[str, Any]],
    api_base: str | None = None,
    max_wait_cycles: int = 3,
    **kwargs: Any,
) -> Any:
    """Call Router and wait/retry when all deployments are cooling down."""
    router = _router_for(model, api_base)
    last_error: Exception | None = None
    for cycle in range(max_wait_cycles):
        try:
            print("[LLM] Rate limiter: waiting 4s before request...")
            time.sleep(4)
            return router.completion(model=model, messages=messages, **kwargs)
        except Exception as error:
            last_error = error
            if not looks_like_key_or_rate_error(error) or cycle == max_wait_cycles - 1:
                raise
            if not is_rate_limit_error(error):
                raise
            print(
                f"[LLM] All available keys are busy or rate-limited; "
                f"waiting 60s before retry {cycle + 2}/{max_wait_cycles}..."
            )
            time.sleep(60)
    raise RuntimeError(f"LLM Router failed after retries: {last_error}")
