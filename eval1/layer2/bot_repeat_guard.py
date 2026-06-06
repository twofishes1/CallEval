from __future__ import annotations

import re
from typing import Iterable, List, Sequence

# 同族表述归并为 signature id，避免「有事再联系」vs「有需要再联系我」漏检
_SIGNATURE_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("defer_contact", ("有需要再联系", "有事再联系", "再联系我", "再联系")),
    ("confirm_step", ("请确认当前步骤", "确认当前步骤", "确认一下")),
    ("safety_remind", ("注意安全", "有单就接", "别拒单", "配送顺利", "祝你顺利")),
)

_BUSY_USER_MARKERS = (
    "没空",
    "没时间",
    "忙",
    "别找",
    "别说了",
    "不说了",
    "挂了",
    "不接",
    "不方便",
    "简短点",
)


def extract_signatures(text: str) -> set[str]:
    t = (text or "").strip()
    out: set[str] = set()
    for fam_id, phrases in _SIGNATURE_FAMILIES:
        if any(p in t for p in phrases):
            out.add(fam_id)
    return out


def is_busy_or_refuse_user(text: str) -> bool:
    u = (text or "").strip()
    return any(m in u for m in _BUSY_USER_MARKERS)


def is_semantically_repetitive(candidate: str, history: Sequence[str]) -> bool:
    """True if candidate reuses closing/deferral phrasing already said by bot."""
    c = (candidate or "").strip()
    if not c or not history:
        return False
    if c == history[-1].strip():
        return True
    if history.count(c) >= 2:
        return True
    if len(c) >= 8 and any(c[:8] == h[:8] for h in history if len(h) >= 8):
        return True
    sig_c = extract_signatures(c)
    if not sig_c:
        return False
    for h in history[-6:]:
        sig_h = extract_signatures(h)
        if sig_c & sig_h:
            return True
    return False


def pick_non_repeating(
    options: Iterable[str],
    history: Sequence[str],
    *,
    attempt: int = 0,
) -> str:
    opts = [str(o).strip() for o in options if str(o).strip()]
    if not opts:
        return "好的，再见。"
    for opt in opts:
        if opt not in history and not is_semantically_repetitive(opt, history):
            return opt
    for opt in opts:
        if not is_semantically_repetitive(opt, history):
            return opt
    return opts[attempt % len(opts)]


def busy_user_reply_alts() -> List[str]:
    return [
        "理解，您先忙，这边先不打扰了。",
        "好的，您方便时再考虑，再见。",
        "明白，先不占用您时间了。",
    ]


def format_repeat_guard_hint(history: Sequence[str], *, limit: int = 4) -> str:
    recent = [h for h in history[-limit:] if h]
    if not recent:
        return ""
    sigs: List[str] = []
    fam_labels = {
        "defer_contact": "再联系/有事联系类收口",
        "confirm_step": "请确认当前步骤类",
        "safety_remind": "安全提醒/别拒单类",
    }
    for h in recent:
        for fid in extract_signatures(h):
            label = fam_labels.get(fid, fid)
            if label not in sigs:
                sigs.append(label)
    lines = " | ".join(recent[-2:])
    ban = f"禁止再用：{'、'.join(sigs)}" if sigs else ""
    return f"你最近说过：{lines}。{ban}。必须换全新措辞，勿复述。"
