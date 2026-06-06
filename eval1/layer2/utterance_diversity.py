from __future__ import annotations

from typing import List

from eval1.layer2.persona import PersonaCard


def _opener(text: str, n: int = 2) -> str:
    u = (text or "").strip()
    return u[:n] if len(u) >= n else u


def _closer(text: str, n: int = 4) -> str:
    u = (text or "").strip()
    return u[-n:] if len(u) >= n else u


def check_utterance_variety(
    utterance: str,
    user_history: List[str],
    *,
    persona: PersonaCard | None = None,
) -> str:
    """Generic anti-repetition: structural similarity only, no phrase blacklist."""
    u = (utterance or "").strip()
    if not u:
        return "空回复"
    history = [str(h).strip() for h in (user_history or []) if str(h).strip()]
    if not history:
        return ""

    if u in history:
        return "与之前说过的话完全相同，请换种表达"

    last = history[-1]
    if len(u) >= 6 and len(last) >= 6:
        if u[:6] == last[:6]:
            return "句首与上一轮太像，请换说法"
        if u[-6:] == last[-6:]:
            return "句尾与上一轮太像，请换说法"

    recent = history[-4:]
    cur_opener = _opener(u)
    if cur_opener and len(cur_opener) >= 2:
        opener_hits = sum(1 for h in recent if _opener(h) == cur_opener)
        if opener_hits >= 2:
            return "最近几轮句首重复，请换种开场方式"

    cur_closer = _closer(u)
    if cur_closer and len(cur_closer) >= 2:
        closer_hits = sum(1 for h in recent if _closer(h) == cur_closer)
        if closer_hits >= 2:
            return "最近几轮句尾重复，请换种收尾方式"

    return ""


# Backward-compatible alias
check_phrase_diversity = check_utterance_variety


def build_diversity_prompt_block(
    user_history: List[str],
    *,
    persona: PersonaCard,
    turn_index: int = 1,
) -> str:
    """Inject persona role design + recent lines; no fixed phrase templates."""
    history = [str(h).strip() for h in (user_history or []) if str(h).strip()]
    traits = "、".join(persona.utterance_patterns or []) or "自然口语"
    lines: List[str] = [
        "【表达多样性】每轮自主措辞，勿复读最近说过的话或固定句式。",
        f"情绪：{persona.emotion_description}",
        f"行为取向：{persona.system_prompt_fragment}",
        f"表达特征：{traits}",
    ]
    if history:
        lines.append("你最近说过（勿复读同样开头、结尾或整句）：")
        for i, h in enumerate(history[-4:], 1):
            lines.append(f"  {i}. {h[:40]}")
    if turn_index >= 4:
        lines.append("通话已多轮，请针对对方最新信息回应，避免重复催促或重复表态。")
    return "\n".join(lines)
