from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, List, Optional, Tuple, TypeVar

from eval1.config import settings
from eval1.qwen_client import chat_with_retry

log = logging.getLogger(__name__)

T = TypeVar("T")


class RobustLLMCall:
    """
    Unified LLM call wrapper: retry, timeout, validator, degradation logging.
    Every judgment point should declare a safe fallback_value.
    """

    def __init__(self, *, component: str = "llm") -> None:
        self.component = component
        self.degraded_calls: List[str] = []

    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        attempts: int = 2,
        timeout_s: float | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        provider_label: str = "Qwen",
    ) -> str:
        timeout = float(timeout_s if timeout_s is not None else settings.llm_request_timeout_sec)

        async def _run() -> str:
            return await asyncio.wait_for(
                chat_with_retry(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    temperature=temperature,
                    api_key=api_key,
                    api_base=api_base,
                    provider_label=provider_label,
                    attempts=attempts,
                    timeout_s=timeout,
                ),
                timeout=timeout + 2.0,
            )

        return await _run()

    async def call_with_fallback(
        self,
        *,
        primary_fn: Callable[[], Any],
        fallback_value: T,
        validator: Callable[[Any], bool],
        max_retry: int = 2,
        timeout: float = 15.0,
        tag: str = "",
    ) -> Tuple[T, str]:
        """
        Returns (result, status) where status is 'success' or 'degraded'.
        """
        label = tag or self.component
        for attempt in range(max(1, max_retry)):
            try:
                async with asyncio.timeout(timeout):
                    result = await primary_fn()
                if validator(result):
                    return result, "success"
                log.warning("[%s] invalid result attempt=%s", label, attempt + 1)
            except asyncio.TimeoutError:
                log.warning("[%s] timeout attempt=%s", label, attempt + 1)
            except Exception as exc:  # noqa: BLE001
                log.error("[%s] error attempt=%s: %s", label, attempt + 1, exc)

        self.degraded_calls.append(label)
        return fallback_value, "degraded"

    def drain_degraded(self) -> List[str]:
        out = list(self.degraded_calls)
        self.degraded_calls.clear()
        return out
