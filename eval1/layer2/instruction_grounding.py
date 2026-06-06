from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

from eval1.layer2.bot_repeat_guard import is_busy_or_refuse_user
from eval1.layer2.instruction_injection import compress_step_to_utterance, substitute_variables
from eval1.layer2.instruction_profile import build_closing_reply_alts_for_profile, build_instruction_profile

_TOPIC_HINTS: Dict[str, Tuple[str, ...]] = {
    "continuous_days": ("连续", "几天", "3天", "名额", "占用", "坚持"),
    "order_quota": ("单", "几单", "多少单", "完单", "单量"),
    "cancel": ("退出", "取消", "不跑", "放弃"),
    "reward": ("奖励", "额外", "补贴"),
    "ranking": ("排名", "拒单", "超时", "站长", "依据", "为什么", "规定", "谁定", "公平", "运气", "混口饭"),
    "live_stream": ("直播", "低延迟", "标准直播", "发课", "带宽", "延迟", "大班", "小班"),
    "peak_hours": ("高峰", "几点", "时段", "上线时间", "什么时候"),
    "contract_start": ("生效", "开始", "配送", "能跑", "上线"),
    "safety": ("安全", "注意"),
}

_TIME_PATTERN = re.compile(r"\d{1,2}\s*[点时:：\-—]\s*\d{0,2}")
_NUMBER_UNIT_PATTERN = re.compile(r"\d+\s*[单点天元%]")


@dataclass
class InstructionGrounding:
    corpus: str
    snippets: List[str] = field(default_factory=list)
    boundary_phrase: str = "我向同事确认后再回电给你。我现在能回答的先回答。"
    slots: Dict[str, str] = field(default_factory=dict)


def _collect_snippets(instruction: Any, slots: Dict[str, str]) -> List[str]:
    parts: List[str] = []
    for attr in ("opening_line", "role_description", "task_description"):
        text = str(getattr(instruction, attr, "") or "").strip()
        if text:
            parts.append(substitute_variables(text, slots))
    for step in list(getattr(instruction, "flow_steps", []) or []):
        t = str(step).strip()
        if t:
            parts.append(substitute_variables(t, slots))
    for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
        t = str(getattr(kn, "text", kn) if not isinstance(kn, dict) else kn.get("text", "")).strip()
        if t:
            parts.append(substitute_variables(t, slots))
    for c in list(getattr(instruction, "constraints", []) or []):
        t = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", "")).strip()
        if t:
            parts.append(substitute_variables(t, slots))
    return parts


def _extract_boundary_phrase(instruction: Any) -> str:
    for c in list(getattr(instruction, "constraints", []) or []):
        text = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", ""))
        m = re.search(r"[「\"]([^」\"]+)[」\"]", text)
        if m and "同事" in text:
            return m.group(1).strip()
    return "我向同事确认后再回电给你。我现在能回答的先回答。"


def build_instruction_grounding(instruction: Any, slots: Dict[str, str] | None = None) -> InstructionGrounding:
    slots = dict(slots or {})
    snippets = _collect_snippets(instruction, slots)
    corpus = "\n".join(snippets)
    return InstructionGrounding(
        corpus=corpus,
        snippets=snippets,
        boundary_phrase=_extract_boundary_phrase(instruction),
        slots=slots,
    )


_OOB_MARKERS = ("下雨", "天气", "头盔", "修路", "奶茶", "工资", "煎饼")


def _question_topics(question: str) -> List[str]:
    q = (question or "").strip()
    if any(m in q for m in _OOB_MARKERS):
        return []
    topics: List[str] = []
    for name, hints in _TOPIC_HINTS.items():
        if any(h in q for h in hints):
            topics.append(name)
    return topics


def _score_snippet(question: str, snippet: str, topics: List[str]) -> int:
    score = 0
    q = question or ""
    for ch in q:
        if len(ch.strip()) >= 2 and ch in snippet:
            score += 1
    for topic in topics:
        hints = _TOPIC_HINTS.get(topic, ())
        if any(h in snippet for h in hints):
            score += 3
        if any(h in q and h in snippet for h in hints):
            score += 2
    if "？" in q or "?" in q or "吗" in q:
        if any(k in q for k in ("为什么", "依据", "什么")) and any(k in snippet for k in ("排名", "合同", "名额", "单")):
            score += 2
    return score


def match_instruction_snippets(
    question: str,
    grounding: InstructionGrounding,
    *,
    limit: int = 2,
) -> List[str]:
    topics = _question_topics(question)
    if not topics:
        return []
    ranked = sorted(
        grounding.snippets,
        key=lambda s: _score_snippet(question, s, topics),
        reverse=True,
    )
    out: List[str] = []
    for s in ranked:
        score = _score_snippet(question, s, topics)
        if score < 3:
            continue
        if s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _shorten_for_phone(text: str, max_len: int = 22) -> str:
    t = re.sub(r"\s+", "", (text or "").strip())
    for sep in ("。", "；", ";", "，", ","):
        if sep in t:
            t = t.split(sep)[0].strip()
            break
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def build_grounded_reply_hint(
    *,
    question: str,
    grounding: InstructionGrounding,
    current_step_text: str,
    current_state: str,
) -> str:
    matched = match_instruction_snippets(question, grounding)
    step_line = compress_step_to_utterance(current_step_text, slots=grounding.slots)
    if matched:
        cites = "\n".join(f"- {s}" for s in matched)
        return (
            f"用户问：「{question}」\n"
            f"【可引用原文（不得超出以下内容）】\n{cites}\n"
            f"当前步骤({current_state})：{current_step_text}\n"
            f"先用1句基于上述原文回答，再自然推进：{step_line}\n"
            "禁止编造具体时间点、单量、天数、规则；原文没有的细节不能说。"
        )
    return (
        f"用户问：「{question}」\n"
        f"任务指令中没有该问题的具体答案。必须先使用边界话术：「{grounding.boundary_phrase}」\n"
        f"然后推进当前步骤({current_state})：{step_line}\n"
        "禁止编造任何业务细节（尤其禁止编造高峰期具体几点）。"
    )


def build_deterministic_grounded_reply(
    *,
    question: str,
    grounding: InstructionGrounding,
    current_step_text: str,
) -> str:
    matched = match_instruction_snippets(question, grounding)
    step_line = compress_step_to_utterance(current_step_text, slots=grounding.slots)
    if matched:
        cite = _shorten_for_phone(matched[0])
        if step_line and step_line not in cite:
            combined = f"{cite} {step_line}"
            return combined[:29] + "。" if len(combined) > 30 else combined
        return cite if cite.endswith(("。", "！", "？", "?", "！")) else f"{cite}。"
    boundary = _shorten_for_phone(grounding.boundary_phrase, max_len=18)
    combined = f"{boundary} {step_line}"
    return combined[:29] + "。" if len(combined) > 30 else combined


def find_constraint_lines(instruction: Any, *needles: str) -> List[str]:
    """Extract constraint lines from parsed instruction (data.xlsx Constraints)."""
    out: List[str] = []
    for c in list(getattr(instruction, "constraints", []) or []):
        t = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", "")).strip()
        if t and any(n in t for n in needles):
            out.append(t)
    return out


def _split_clauses(text: str) -> List[str]:
    parts = re.split(r"[。；;！!？?]", text or "")
    out: List[str] = []
    for p in parts:
        s = re.sub(r"^(说明|告知|提醒|尽量)", "", p.strip()).strip()
        if len(s) >= 4:
            out.append(s)
    return out


def build_step_utterance_alts(
    instruction: Any,
    current_state: str,
    step_text: str,
    slots: Dict[str, str] | None = None,
    *,
    max_len: int = 30,
) -> List[str]:
    """Phone-length phrasing candidates derived from Call Flow + FAQ in instruction."""
    from eval1.layer2.instruction_injection import (
        build_f2_single_utterance,
        build_f4_single_utterance,
        compress_step_to_utterance,
        instruction_f4_is_delivery_split,
        _is_meta_step_line,
    )

    slots = dict(slots or {})
    resolved = substitute_variables(step_text or "", slots)
    alts: List[str] = []

    if str(current_state).startswith("branch::") and instruction:
        from eval1.layer2.step_speakable import resolve_branch_speakable

        spoken = resolve_branch_speakable(instruction, current_state, slots, max_len=max_len)
        if spoken and spoken not in alts:
            alts.append(spoken)

    if current_state == "F4":
        primary = build_f4_single_utterance(resolved, slots=slots, instruction=instruction)
        if primary and primary not in alts:
            alts.append(primary)

    if current_state.startswith("F"):
        try:
            from eval1.layer2.step_speakable import pick_step_speakable, _step_title_needs_script

            idx = int(current_state[1:])
            if _step_title_needs_script(resolved):
                spoken = pick_step_speakable(
                    instruction, idx, resolved, slots=slots, max_len=max_len
                )
                if spoken and spoken not in alts:
                    alts.insert(0, spoken)
        except ValueError:
            pass

    if current_state == "F2":
        primary = build_f2_single_utterance(resolved, slots=slots, instruction=instruction)
        if primary and primary not in alts:
            alts.append(primary)

    for clause in _split_clauses(resolved):
        if _is_meta_step_line(clause):
            continue
        short = _shorten_for_phone(clause, max_len - 1)
        line = short if short.endswith(("。", "！", "？", "?", "！")) else f"{short}。"
        if line and line not in alts and len(line.replace(" ", "")) >= 6:
            alts.append(line)

    # FAQ 仅在 FAQ 节点注入候选；主流程 F1–F4 不得混入 K1 等知识库片段（避免 F3 误说「许多骑手申请」）
    if current_state in {"FAQ_NORMAL", "FAQ_OOB"}:
        for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
            raw = str(getattr(kn, "text", kn) if not isinstance(kn, dict) else kn.get("text", ""))
            t = substitute_variables(raw, slots)
            short = _shorten_for_phone(t, max_len - 1)
            line = short if short.endswith(("。", "！", "？", "?", "！")) else f"{short}。"
            if line and line not in alts:
                alts.append(line)
    elif current_state in {"OBJECTION", "F3_RETAIN"}:
        state_faq_hints = {
            "OBJECTION": ("排名", "名额", "连续", "合同"),
            "F3_RETAIN": ("安全", "配送", "名额"),
        }
        hints = state_faq_hints.get(current_state, ())
        for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
            raw = str(getattr(kn, "text", kn) if not isinstance(kn, dict) else kn.get("text", ""))
            t = substitute_variables(raw, slots)
            if hints and not any(h in t for h in hints):
                continue
            short = _shorten_for_phone(t, max_len - 1)
            line = short if short.endswith(("。", "！", "？", "?", "！")) else f"{short}。"
            if line and line not in alts:
                alts.append(line)

    if not alts:
        base = compress_step_to_utterance(
            resolved, slots=slots, max_len=max_len, current_state=current_state
        )
        if base:
            alts.append(base)
    return alts


def build_objection_reply_hint(
    *,
    instruction: Any,
    grounding: InstructionGrounding,
    question: str,
    current_state: str,
    current_step_text: str,
) -> str:
    """Prompt hint when user objects — follow data Constraints + FAQ, no verbatim repeat."""
    no_repeat = find_constraint_lines(instruction, "重复", "重申")
    hangup = find_constraint_lines(instruction, "挂断", "无法配送")
    faq = match_instruction_snippets(question, grounding)
    parts = [f"用户有顾虑：「{question}」"]
    if no_repeat:
        parts.append(f"【Constraints】{no_repeat[0]}")
    parts.append(
        "禁止逐字重复上一轮Bot话术或Call Flow整句；如需重申，必须换种方式礼貌表达。"
    )
    if faq:
        cites = "\n".join(f"- {s}" for s in faq)
        parts.append(f"优先引用Knowledge/FAQ原文换种说法（勿照读整段）：\n{cites}")
    else:
        alts = build_step_utterance_alts(
            instruction, current_state, current_step_text, grounding.slots
        )
        if len(alts) > 1:
            parts.append("可从指令拆成不同角度，每次只说一点：\n" + "\n".join(f"- {a}" for a in alts[:4]))
        else:
            step_line = compress_step_to_utterance(
                current_step_text, slots=grounding.slots, current_state=current_state
            )
            parts.append(f"换种方式说明当前步骤({current_state})：{step_line}")
    if hangup and any(k in question for k in ("不签", "无法", "配送不了", "做不到", "不想签")):
        parts.append(f"【Constraints】{hangup[0]}")
    if current_state in {"F3_RETAIN", "F3", "OBJECTION"}:
        retain = find_constraint_lines(instruction, "挽留", "鼓励")
        if retain:
            parts.append(f"【Call Flow·挽留】{retain[0]}")
        parts.append(
            "输出必须含实质挽留：理解顾虑 + 鼓励继续配送/说明好处 + 安全提醒，"
            "不要空泛套话。"
        )
    return "\n".join(parts)


def build_hangup_reply_alts(instruction: Any, *, last_user_utterance: str = "") -> List[str]:
    """Comfort + hangup lines aligned with Constraints in data instruction."""
    from eval1.layer2.constraint_scenarios import build_driving_hangup_alts, is_driving_user

    if is_driving_user(last_user_utterance):
        return build_driving_hangup_alts(instruction)
    hangup = find_constraint_lines(instruction, "挂断", "无法配送")
    _ = hangup
    return [
        "理解您的难处，先不打扰了，再见。",
        "好的，那您先忙，祝您顺利。",
        "明白，这边先挂了，您保重。",
    ]


_REFUSE_MARKERS = ("不送", "不接", "做不了", "没法", "不行", "不想", "拒绝", "配送不了", "跑不了")
_FAQ_LEAK_MARKERS = ("许多骑手", "单日合同", "多日合同", "22点", "飞毛腿报名", "名额可能会被")
_FLOW_STATES_NO_FAQ = frozenset({"F1", "F2", "F3", "F4", "CLOSING"})


def is_faq_leak_on_flow_step(current_state: str, text: str) -> bool:
    """True when bot cites FAQ/Knowledge on a mainline Call Flow step (not FAQ_NORMAL)."""
    state = str(current_state or "")
    if state not in _FLOW_STATES_NO_FAQ:
        return False
    t = (text or "").strip()
    return bool(t) and any(m in t for m in _FAQ_LEAK_MARKERS)
_SYMPATHY_HANGUP_MARKERS = ("理解您的难处", "理解，您先忙", "配送不了", "没法配送", "先不打扰了")


def infer_closing_tone(
    *,
    last_user_utterance: str,
    user_action: str,
    consecutive_reject: int = 0,
    dialogue_history: Sequence[Dict[str, str]] | None = None,
    covered_nodes: Sequence[str] | None = None,
) -> str:
    """cooperative | neutral | refused | busy — drives context-appropriate goodbye."""
    from eval1.layer2.constraint_scenarios import is_driving_user

    action = str(user_action or "comply")
    last = (last_user_utterance or "").strip()
    if action == "hangup" or is_driving_user(last):
        return "busy"
    if is_busy_or_refuse_user(last):
        return "busy"
    user_msgs = [
        str(m.get("content", ""))
        for m in (dialogue_history or [])
        if str(m.get("role", "")).lower() == "user"
    ]
    recent = user_msgs[-3:]
    if any(any(m in u for m in _REFUSE_MARKERS) for u in recent[-2:]):
        if action not in {"comply", "confirm"}:
            return "refused"
    nodes = set(covered_nodes or [])
    if nodes & {"OBJ_FINAL", "F3_RETAIN", "OBJECTION"}:
        if action in {"comply", "confirm"} and consecutive_reject <= 1:
            return "neutral"
        if consecutive_reject >= 2 or action == "reject":
            return "refused"
    if consecutive_reject >= 2:
        return "neutral"
    if action in {"comply", "confirm"}:
        return "cooperative"
    return "neutral"


def build_closing_reply_alts(
    instruction: Any,
    tone: str,
    *,
    last_user_utterance: str = "",
) -> List[str]:
    """Context-aware closing lines derived from instruction profile."""
    _ = last_user_utterance
    profile = build_instruction_profile(instruction, {})
    if tone in {"busy", "refused"}:
        return build_hangup_reply_alts(instruction, last_user_utterance=last_user_utterance)
    return build_closing_reply_alts_for_profile(profile, tone)


def build_closing_reply_hint(
    *,
    closing_tone: str,
    last_user_utterance: str,
    instruction: Any | None = None,
) -> str:
    last = (last_user_utterance or "").strip() or "已确认"
    if closing_tone == "cooperative":
        profile = build_instruction_profile(instruction, {})
        callee = profile.user_role
        wish = profile.closing_wish
        return (
            f"用户已配合确认：「{last}」\n"
            f"【收口任务】通话目标已达成。简短肯定{callee}配合，可祝{wish}或提醒后续操作，"
            "礼貌道别挂断（≤30字）。"
            "禁止说「理解您的难处」「先不打扰了」等婉拒/同情话术；"
            "禁止引用FAQ或复述整段条款；"
            f"禁止出现与当前任务无关的表述：{'、'.join(profile.forbidden_phrases[:8]) or '无'}。"
        )
    if closing_tone in {"busy", "refused"}:
        return (
            f"用户不便或拒绝继续：「{last}」\n"
            "【收口任务】简短表示理解，礼貌告别挂断（≤30字）。"
            "不要继续催接单或重复业务要求。"
        )
    return (
        f"用户回应：「{last}」\n"
        "【收口任务】根据对话走向简短总结并道别（≤30字）。"
        "禁止引用FAQ知识库条目；不要重复已说过的合同细节。"
    )


def is_bad_closing_response(text: str, tone: str) -> bool:
    t = (text or "").strip()
    if not t or len(t.replace(" ", "")) > 32:
        return True
    if any(m in t for m in _FAQ_LEAK_MARKERS):
        return True
    if tone == "cooperative" and any(m in t for m in _SYMPATHY_HANGUP_MARKERS):
        return True
    if not any(x in t for x in ("再见", "拜拜", "先这样", "不打扰", "先挂", "祝您", "顺利", "加油", "保重")):
        return True
    return False


def is_grounded_in_instruction(text: str, grounding: InstructionGrounding) -> bool:
    utter = (text or "").strip()
    if not utter:
        return False
    corpus = grounding.corpus or ""

    for m in _TIME_PATTERN.findall(utter):
        compact = re.sub(r"\s+", "", m)
        if compact and compact not in re.sub(r"\s+", "", corpus):
            return False

    for m in _NUMBER_UNIT_PATTERN.findall(utter):
        compact = re.sub(r"\s+", "", m)
        if compact and compact not in re.sub(r"\s+", "", corpus):
            # allow slot-substituted values explicitly present in corpus
            num = re.search(r"\d+", compact)
            if num and num.group(0) not in corpus:
                return False

    banned_phrases = ("11点", "13点", "17点", "19点", "11-13", "17-19", "11：", "13：")
    for bp in banned_phrases:
        if bp in utter and bp not in corpus:
            return False
    return True
