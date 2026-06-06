from __future__ import annotations

from eval1.bot_provider import BOT_PROVIDER_QWEN, get_bot_provider
from eval1.config import settings
from eval1.qwen_client import reset_llm_semaphore


def apply_fast_mode(*, enabled: bool = True) -> dict[str, object]:
    """Tune runtime settings for faster eval (turbo models, higher concurrency, fewer retries)."""
    if not enabled:
        return {"fast_mode": False}
    applied: dict[str, object] = {"fast_mode": True}
    if settings.llm_model_fast in {"", "qwen-plus"}:
        settings.llm_model_fast = "qwen-turbo"
        applied["llm_model_fast"] = "qwen-turbo"
    if get_bot_provider() == BOT_PROVIDER_QWEN and settings.llm_model_main in {"", "qwen-plus", "qwen-max"}:
        settings.llm_model_main = "qwen-turbo"
        applied["llm_model_main"] = "qwen-turbo"
    if settings.llm_model_judge in {"", "qwen-plus", "qwen-max"}:
        settings.llm_model_judge = "qwen-turbo"
        applied["llm_model_judge"] = "qwen-turbo"
    settings.llm_max_concurrent = max(int(settings.llm_max_concurrent), 10)
    settings.max_concurrent_dialogues = max(int(settings.max_concurrent_dialogues), 4)
    settings.action_verify_max_retry = 0
    settings.llm_robust_max_retry = 1
    settings.llm_request_timeout_sec = min(float(settings.llm_request_timeout_sec), 35.0)
    settings.llm_dialogue_timeout_sec = min(float(getattr(settings, "llm_dialogue_timeout_sec", 28.0)), 22.0)
    reset_llm_semaphore()
    applied["llm_max_concurrent"] = settings.llm_max_concurrent
    applied["max_concurrent_dialogues"] = settings.max_concurrent_dialogues
    return applied
