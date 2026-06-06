from __future__ import annotations

import asyncio
import json
import ssl
from typing import Any, Dict, List
from urllib import error as urlerror
from urllib import request

from eval1.config import settings

_llm_semaphore: asyncio.Semaphore | None = None


def reset_llm_semaphore() -> None:
    """Recreate global LLM semaphore after runtime tuning changes concurrency."""
    global _llm_semaphore
    _llm_semaphore = asyncio.Semaphore(max(1, int(settings.llm_max_concurrent)))


def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        reset_llm_semaphore()
    return _llm_semaphore


def _resolve_api_key(*, api_key: str | None = None) -> str:
    return (api_key if api_key is not None else settings.dashscope_api_key or "").strip()


def is_transient_llm_error(exc: BaseException) -> bool:
    """Network/SSL blips from DashScope or local stack — safe to retry briefly."""
    if isinstance(exc, (ssl.SSLError, ConnectionResetError, TimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, urlerror.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (ssl.SSLError, ConnectionResetError, OSError, TimeoutError)):
            return True
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "ssl",
            "unexpected_eof",
            "eof occurred",
            "connection reset",
            "timed out",
            "temporarily unavailable",
            "connection aborted",
        )
    )


def _chat_once(
    *,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    timeout_s: float | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    provider_label: str = "LLM",
) -> str:
    key = _resolve_api_key(api_key=api_key)
    if not key:
        raise RuntimeError(f"{provider_label} API key is not configured for eval1.")
    base = (api_base if api_base is not None else settings.qwen_api_base).rstrip("/")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=f"{base}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    wait_s = float(timeout_s if timeout_s is not None else settings.llm_request_timeout_sec)
    with request.urlopen(req, timeout=wait_s) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider_label} response has no choices.")
    msg = (choices[0].get("message") or {}).get("content")
    if not isinstance(msg, str) or not msg.strip():
        raise RuntimeError(f"{provider_label} response has empty content.")
    return msg.strip()


async def chat_with_retry(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    attempts: int = 3,
    base_delay_s: float = 0.5,
    timeout_s: float | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    provider_label: str = "Qwen",
) -> str:
    last_err: Exception | None = None
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    sem = _get_llm_semaphore()
    max_attempts = max(1, int(attempts))
    wait_s = float(
        timeout_s
        if timeout_s is not None
        else getattr(settings, "llm_dialogue_timeout_sec", None) or settings.llm_request_timeout_sec
    )
    for i in range(max_attempts):
        try:
            async with sem:
                return await asyncio.to_thread(
                    _chat_once,
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    timeout_s=wait_s,
                    api_key=api_key,
                    api_base=api_base,
                    provider_label=provider_label,
                )
        except Exception as e:  # noqa: BLE001
            last_err = e
            retryable = is_transient_llm_error(e)
            if i + 1 < max_attempts and retryable:
                await asyncio.sleep(base_delay_s * (2**i))
                continue
            if not retryable:
                break
    assert last_err is not None
    raise last_err
