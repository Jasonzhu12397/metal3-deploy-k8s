"""
Talks to whatever OpenAI-compatible endpoint a stored LLMProviderCredential
points at. One client for OpenAI, DeepSeek, Qwen (DashScope compatible
mode), Doubao (Volcengine Ark), and any custom endpoint, because they all
implement the same wire format on purpose -- this is also exactly the
protocol vLLM's own OpenAI-compatible server speaks, so this same client
shape is reusable once a self-hosted vLLM deployment exists too.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

DEFAULT_TIMEOUT_SECONDS = 15.0


class LLMProviderError(RuntimeError):
    pass


async def test_connection(base_url: str, api_key: str, model: Optional[str]) -> dict:
    """Fires the smallest possible real request (1-token chat completion,
    not just a bare GET) so this actually proves the key/base_url/model
    combination works end to end, not just that the host is reachable.
    Some OpenAI-compatible providers don't implement GET /models
    correctly even when chat completions works fine, so that's
    deliberately not what this checks.

    Returns a dict matching schemas.llm_provider.LLMProviderTestResult's
    fields -- never raises for a failed *provider* response (bad key,
    bad model, etc.), only for things that mean the test itself couldn't
    run (network unreachable, malformed base_url). Callers should surface
    ok=False + error to the user either way; the distinction only matters
    for logging.
    """
    if not model:
        # Every one of the four known providers has at least one
        # inexpensive/free-tier chat model available under a predictable
        # name for exactly this kind of smoke test.
        model = "gpt-4o-mini" if "openai.com" in base_url else "default"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url.rstrip('/')}/chat/completions"

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.RequestError as exc:
        return {"ok": False, "latency_ms": None, "model_used": model, "error": f"network error: {exc}"}

    latency_ms = round((time.monotonic() - started) * 1000, 1)

    if resp.status_code == 200:
        return {"ok": True, "latency_ms": latency_ms, "model_used": model, "error": None}

    # Surface the provider's own error message when there is one (every
    # OpenAI-compatible error body has an {"error": {"message": ...}}
    # shape) -- "401" alone doesn't tell anyone whether it's a bad key, a
    # bad model name, or something else.
    try:
        body = resp.json()
        message = body.get("error", {}).get("message") or str(body)
    except Exception:  # noqa: BLE001
        message = resp.text[:200]

    return {
        "ok": False,
        "latency_ms": latency_ms,
        "model_used": model,
        "error": f"HTTP {resp.status_code}: {message}",
    }
