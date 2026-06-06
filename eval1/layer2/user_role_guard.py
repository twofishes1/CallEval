from __future__ import annotations

import re
from typing import List, Sequence

# User must not speak with caller/bot voice (announce upgrades, 告知, etc.)
_CALLER_VOICE_MARKERS = (
    "我们对",
    "我们做了升级",
    "我们这边做了升级",
    "新增了独立",
    "告知机构",
    "发课时选",
    "参考话术",
    "进入第",
    "Call Flow",
)

# Topics the user should not volunteer before the caller mentions them in dialogue.
_PREMATURE_TOPIC_KEYS = (
    "做了升级",
    "新增了",
    "低延迟直播",
    "标准直播",
    "发布页会分开",
    "走低延迟线路",
)


def user_facing_task_summary(active_domains: Sequence[str], user_role: str = "") -> str:
    """Listener-side scene summary — never inject the bot's task script."""
    if "education_live" in active_domains:
        return "对方来电沟通课程发布/直播相关事项，具体细节等对方说明后再回应"
    if "delivery" in active_domains:
        return "站长来电沟通配送/合同相关事项，具体细节等对方说明后再回应"
    if "负责人" in user_role:
        return "对方来电沟通业务相关事项，具体细节等对方说明后再回应"
    return "对方来电沟通业务相关事项，按对方已说的内容回应即可"


def _bot_said_so_far(last_bot: str, bot_history: List[str] | None) -> str:
    parts = [str(x).strip() for x in (bot_history or []) if str(x).strip()]
    if last_bot and last_bot.strip() not in parts:
        parts.append(last_bot.strip())
    return " ".join(parts)


def is_caller_role_leak(
    utterance: str,
    *,
    last_bot: str = "",
    bot_history: List[str] | None = None,
    current_state: str = "",
) -> bool:
    """True when user speaks as the caller (e.g. announcing upgrades unprompted)."""
    u = (utterance or "").strip()
    if not u:
        return False
    if any(m in u for m in _CALLER_VOICE_MARKERS):
        return True
    if re.search(r"^我们(对|的|这边)", u):
        return True
    corpus = _bot_said_so_far(last_bot, bot_history)
    early = current_state in {"START", "F1"} or not corpus.strip()
    if not early:
        return False
    for key in _PREMATURE_TOPIC_KEYS:
        if key in u and key not in corpus:
            return True
    if early and any(k in u for k in ("升级", "低延迟", "标准直播")) and not any(
        k in corpus for k in ("升级", "低延迟", "标准直播")
    ):
        return True
    return False


_IDENTITY_ACK_LINES = frozenset(
    {"是的，我是。", "对，您说。", "对，是我。", "嗯，我负责这块。"}
)


def is_stale_identity_ack(utterance: str, *, last_bot: str, current_state: str) -> bool:
    u = (utterance or "").strip()
    if u not in _IDENTITY_ACK_LINES:
        return False
    bot = (last_bot or "").strip()
    if current_state in {"START", "F1"} and any(k in bot for k in ("负责人", "请问您", "是您")):
        if not any(k in bot for k in ("升级", "低延迟", "标准直播", "发课")):
            return False
    if any(k in bot for k in ("升级", "低延迟", "标准直播", "发课", "选项", "费用")):
        return True
    if current_state not in {"START", "F1"}:
        return True
    return not any(k in bot for k in ("负责人", "请问您", "是您"))


def stale_identity_ack_reason(
    utterance: str,
    *,
    last_bot: str,
    current_state: str,
) -> str:
    if not is_stale_identity_ack(utterance, last_bot=last_bot, current_state=current_state):
        return ""
    return "身份已确认，请针对对方刚说的业务内容回应，勿再用身份确认套话"


def caller_role_leak_reason(
    utterance: str,
    *,
    last_bot: str = "",
    bot_history: List[str] | None = None,
    current_state: str = "",
) -> str:
    if not is_caller_role_leak(
        utterance,
        last_bot=last_bot,
        bot_history=bot_history,
        current_state=current_state,
    ):
        return ""
    return (
        "你是接听方不是客服，禁止替对方宣告升级/产品方案；"
        "对方尚未说明的内容不要主动讲，身份确认阶段只答是否负责人即可"
    )
