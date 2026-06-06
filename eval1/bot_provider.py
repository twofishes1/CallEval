"""被测 Bot 模型提供商：Qwen（默认）与 DeepSeek。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Iterator, List

from eval1.config import settings

BOT_PROVIDER_QWEN = "qwen"
BOT_PROVIDER_DEEPSEEK = "deepseek"
SUPPORTED_BOT_PROVIDERS = (BOT_PROVIDER_QWEN, BOT_PROVIDER_DEEPSEEK)

_current_bot_provider: ContextVar[str] = ContextVar("eval1_bot_provider", default=BOT_PROVIDER_QWEN)

_EVAL1_ROOT = Path(__file__).resolve().parent


def normalize_bot_provider(value: str | None) -> str:
    p = (value or BOT_PROVIDER_QWEN).strip().lower()
    if p not in SUPPORTED_BOT_PROVIDERS:
        raise ValueError(f"Unsupported bot_provider={value!r}; use qwen or deepseek")
    return p


def get_bot_provider() -> str:
    return normalize_bot_provider(_current_bot_provider.get())


@contextmanager
def bot_provider_scope(provider: str | None) -> Iterator[str]:
    p = normalize_bot_provider(provider)
    token = _current_bot_provider.set(p)
    try:
        yield p
    finally:
        _current_bot_provider.reset(token)


def reports_output_path(dataset_id: str, bot_provider: str | None = None) -> Path:
    """Qwen 沿用无后缀文件名；DeepSeek 写入 *_deepseek.json。"""
    ds = str(dataset_id or "").strip()
    p = normalize_bot_provider(bot_provider or get_bot_provider())
    suffix = "" if p == BOT_PROVIDER_QWEN else f"_{p}"
    return _EVAL1_ROOT / "outputs" / f"eval1_reports_{ds}{suffix}.json"


def list_available_report_providers(dataset_id: str) -> List[Dict[str, Any]]:
    ds = str(dataset_id or "").strip()
    rows: List[Dict[str, Any]] = []
    for p in SUPPORTED_BOT_PROVIDERS:
        path = reports_output_path(ds, p)
        rows.append(
            {
                "bot_provider": p,
                "label": bot_provider_label(p),
                "filename": path.name,
                "exists": path.is_file(),
            }
        )
    return rows


def bot_provider_label(provider: str) -> str:
    p = normalize_bot_provider(provider)
    if p == BOT_PROVIDER_DEEPSEEK:
        return "DeepSeek Bot"
    return "Qwen Bot"


def get_bot_llm_profile(provider: str | None = None) -> Dict[str, str]:
    """OpenAI-compatible profile for the bot under test (not user sim / judge)."""
    p = normalize_bot_provider(provider or get_bot_provider())
    if p == BOT_PROVIDER_DEEPSEEK:
        return {
            "bot_provider": p,
            "api_key": (settings.deepseek_api_key or "").strip(),
            "api_base": (settings.deepseek_api_base or "https://api.deepseek.com").rstrip("/"),
            "model": (settings.deepseek_bot_model or "deepseek-chat").strip(),
        }
    return {
        "bot_provider": p,
        "api_key": (settings.dashscope_api_key or "").strip(),
        "api_base": (settings.qwen_api_base or "").rstrip("/"),
        "model": (settings.llm_model_main or "qwen-plus").strip(),
    }
