from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

EVAL_MODE_TAG = (
    "<eval_mode>\n"
    "当前为评测环境。工具调用会被拦截并记录，请按任务指令正常对话。\n"
    "【对话生成原则】\n"
    "1. 每轮须先承接用户/商家上一句，再推进当前 Call Flow 步骤；禁止各说各话。\n"
    "2. 参考话术、分支动作、步骤标题仅作语义参考，禁止照读；须结合上下文自主措辞。\n"
    "3. 用户已确认的内容勿重复；同一要点禁止连续两轮原样复读。\n"
    "4. 保持电话口语、简短自然；仍须覆盖当前步骤应传达的信息，不跳过主流程。\n"
    "</eval_mode>"
)

_REQUIRED_MODULES = (
    ("Role", "role_description"),
    ("Task", "task_description"),
    ("Call Flow", "flow_steps"),
    ("FAQ", "knowledge_nodes"),
    ("Constraints", "constraints"),
    ("Opening Line", "opening_line"),
)

_META_PREFIXES = ("说明", "确认", "提醒", "告知", "询问", "完成")

# Instruction block labels — must never appear in phone speech
_SCRIPT_LABEL_RE = re.compile(
    r"\*{0,2}\s*(?:参考话术|询问)\s*\*{0,2}\s*[：:]+\s*",
    re.IGNORECASE,
)

# F4 三要点一次性完整交付（Call Flow 原文三句拼接，F4 轮次豁免 30 字限制）
F4_DEFAULT_CLAUSES = (
    "飞毛腿报名是按排名进行的，并非站长干预",
    "骑手应减少拒单、取消和超时",
    "在恶劣天气下工作、订单量更高，有助于保住飞毛腿资格",
)

# 超短压缩备选（仅 LLM hint / 旧报告引用）
F4_COMPRESSED_LINE = "飞毛腿按排名录，非站长定；少拒单取消超时，坏天气单多更稳。"

F4_COMPRESSED_ALTS = (
    F4_COMPRESSED_LINE,
    "排名定资格非站长定，少拒单别超时，恶劣天气多接单。",
)

F4_DEFAULT_PARTS = F4_DEFAULT_CLAUSES

F4_PART_META = (
    ("ranking", ("排名", "站长", "干预")),
    ("reject", ("拒单", "取消", "超时")),
    ("weather", ("恶劣天气", "天气", "单量", "保住", "资格")),
)

F4_POST_ACK_ALTS = (
    "好的，按排名接单，注意安全，再见。",
    "收到，少拒单多接单，有问题再打给我，再见。",
    "明白，辛苦了，再见。",
)

_F4_DELIVERY_MARKERS = ("排名", "拒单", "超时", "站长", "恶劣天气", "订单量", "飞毛腿", "派单", "取消")


def instruction_f4_is_delivery_split(
    instruction: Any,
    step_text: str = "",
    slots: Dict[str, str] | None = None,
) -> bool:
    """True only when Call Flow F4 is the rider 3-theme block (ranking/reject/weather)."""
    text = substitute_variables(step_text or "", slots)
    if not text.strip() and instruction is not None:
        steps = list(getattr(instruction, "flow_steps", []) or [])
        if len(steps) >= 4:
            text = substitute_variables(str(steps[3]), slots)
    if instruction is None:
        return _raw_is_delivery_f4(text)
    from eval1.layer2.instruction_profile import build_instruction_profile

    profile = build_instruction_profile(instruction, slots)
    if "delivery" not in profile.active_domains:
        return False
    return _raw_is_delivery_f4(text)


def substitute_variables(text: str, values: Dict[str, str] | None = None) -> str:
    """Replace ${var}, **X**, and bare uppercase tokens in instruction text."""
    out = text or ""
    vals = values or {}

    def _get(name: str, default: str = "") -> str:
        v = str(vals.get(name, "")).strip()
        return v if v else default

    out = re.sub(
        r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}",
        lambda m: _get(m.group(1), m.group(0)),
        out,
    )
    out = re.sub(
        r"\*\*([A-Z])\s*([^*]*?)\*\*",
        lambda m: f"{_get(m.group(1), m.group(1))}{m.group(2)}",
        out,
    )
    out = re.sub(
        r"(?<![A-Za-z0-9_])([A-Z])(?![A-Za-z0-9_])",
        lambda m: _get(m.group(1), m.group(1)),
        out,
    )
    return out


def check_instruction_completeness(instruction: Any) -> List[str]:
    """Verify six modules exist; return warning messages for missing ones."""
    warnings: List[str] = []
    for label, attr in _REQUIRED_MODULES:
        val = getattr(instruction, attr, None)
        if val is None:
            warnings.append(f"缺失模块：{label}")
            continue
        if isinstance(val, list):
            if not val:
                warnings.append(f"缺失模块：{label}")
        elif isinstance(val, str):
            if not str(val).strip():
                warnings.append(f"缺失模块：{label}")
    return warnings


def build_resolved_instruction_document(instruction: Any, slot_values: Dict[str, str] | None = None) -> str:
    """Rebuild task instruction原文 from parsed sections (variables already resolved in parser)."""
    if not instruction:
        return ""
    resolved = str(getattr(instruction, "resolved_text", "") or "").strip()
    if resolved:
        return substitute_variables(resolved, slot_values)

    parts: List[str] = []
    role = str(getattr(instruction, "role_description", "") or "").strip()
    task = str(getattr(instruction, "task_description", "") or "").strip()
    opening = str(getattr(instruction, "opening_line", "") or "").strip()
    if role:
        parts.append(f"## Role\n{role}")
    if task:
        parts.append(f"## Task\n{task}")
    if opening:
        parts.append(f"## Opening Line\n{opening}")

    flow_steps = list(getattr(instruction, "flow_steps", []) or [])
    if flow_steps:
        parts.append("## Call Flow")
        for i, step in enumerate(flow_steps, start=1):
            parts.append(f"{i}. {step}")

    knowledge_nodes = list(getattr(instruction, "knowledge_nodes", []) or [])
    if knowledge_nodes:
        parts.append("## FAQ / Knowledge")
        for kn in knowledge_nodes:
            text = str(getattr(kn, "text", kn) if not isinstance(kn, dict) else kn.get("text", ""))
            if text.strip():
                parts.append(f"- {text.strip()}")

    constraints = list(getattr(instruction, "constraints", []) or [])
    if constraints:
        parts.append("## Constraints")
        for c in constraints:
            txt = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", ""))
            if txt.strip():
                parts.append(f"- {txt.strip()}")

    doc = "\n\n".join(parts)
    return substitute_variables(doc, slot_values)


def build_bot_system_prompt(
    instruction: Any,
    slot_values: Dict[str, str] | None = None,
    *,
    eval_mode: bool = True,
) -> Tuple[str, List[str]]:
    """
    Bot System Prompt = 任务指令原文（变量替换后）+ eval_mode 标记。
    Returns (prompt, completeness_warnings).
    """
    warnings = check_instruction_completeness(instruction)
    body = build_resolved_instruction_document(instruction, slot_values)
    if not body.strip():
        body = str(getattr(instruction, "raw_text", "") or "")
        body = substitute_variables(body, slot_values)
    prompt = body.strip()
    if eval_mode:
        prompt = f"{prompt}\n\n{EVAL_MODE_TAG}"
    return prompt, warnings


def build_bot_instruction_bundle(instruction: Any, slot_values: Dict[str, str] | None = None) -> str:
    """Legacy bundle builder; prefer build_bot_system_prompt for SUT injection."""
    prompt, _ = build_bot_system_prompt(instruction, slot_values, eval_mode=True)
    return prompt


_STEP_LABEL_RE = re.compile(r"^(?:#{1,3}\s*)?(?:step\s*)?\d+[:：\.]\s*", re.IGNORECASE)
_STEP_ANYWHERE_RE = re.compile(r"step\s*\d+\s*[:：]?\s*", re.IGNORECASE)


def _strip_step_label(text: str) -> str:
    t = (text or "").strip()
    prev = None
    while t and t != prev:
        prev = t
        t = _STEP_LABEL_RE.sub("", t).strip()
    return t


def _strip_script_labels(text: str) -> str:
    t = (text or "").strip()
    prev = None
    while t and t != prev:
        prev = t
        t = _SCRIPT_LABEL_RE.sub("", t).strip()
        t = re.sub(r"^\*+\s*", "", t).strip()
    return t


def sanitize_bot_output(text: str) -> str:
    """Remove Step N labels anywhere in bot speech — never readable on a phone call."""
    t = _strip_script_labels((text or "").strip())
    if not t:
        return t
    from eval1.layer2.step_speakable import naturalize_branch_action

    branch_m = re.match(r"^(?:若|如果).+?[→\-]{1,2}\s*(.+?)[。]?$", t)
    if branch_m:
        natural = naturalize_branch_action(branch_m.group(1).strip())
        if natural:
            return natural
    prev = None
    while t and t != prev:
        prev = t
        t = _STEP_LABEL_RE.sub("", t).strip()
        t = _STEP_ANYWHERE_RE.sub("", t).strip()
    t = re.sub(r"\s{2,}", " ", t).strip(" ，,；;")
    return t


def _strip_meta_prefix(text: str) -> str:
    t = _strip_script_labels(_strip_step_label(text))
    for prefix in _META_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    return t


_META_NAV_RE = re.compile(
    r"(进入第\s*\d+\s*步|请其转达|然后进入|参考话术|step\s*\d+)",
    re.IGNORECASE,
)


def _is_meta_step_line(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _STEP_LABEL_RE.match(t):
        return True
    if _META_NAV_RE.search(t):
        return True
    if t.startswith(("若", "如果", "when", "- 若", "—>")):
        return True
    if re.match(r"^步骤\d+$", t):
        return True
    if re.search(r"^(尽量|务必|应当|需要)(挽留|告知|说明|提醒|鼓励)", t):
        return True
    if re.search(r"(挽留|告知|提醒|鼓励).*(的)?骑手", t) and not re.match(r"^(我|您|你|咱)", t):
        return True
    if re.fullmatch(r"挽留不想配送的骑手[。！]?", t):
        return True
    if "不想配送的骑手" in t and len(t.replace(" ", "")) <= 16:
        return True
    return False


# Bot 兜底：按 FSM 状态给可说出口的话，避免「您方便再听我说一句吗」/ 流程元指令直出
_FLOW_STATE_ALTS: Dict[str, tuple[str, ...]] = {
    "F1": ("骑手今天飞毛腿合同已生效，能开始配送吗？",),
    "F2": ("单日飞毛腿需连续3天配送，否则合同会受影响。",),
    "F3": (
        "路上注意安全，能跑尽量跑。",
        "辛苦啦，配送时注意安全。",
        "加油，注意保暖和安全。",
    ),
    "F3_RETAIN": (
        "名额有限，连续3天更稳，您再考虑下？",
        "理解您忙，但跑满3天更划算，要不再试试？",
    ),
    "CLOSING": ("好的，祝您配送顺利，再见。",),
    "FAQ_NORMAL": ("关于您刚问的，我按规则说明一下。",),
    "FAQ_OOB": (
        "我向同事确认后再回电给你。我现在能回答的先回答。",
        "这个我帮您确认，先把飞毛腿的事说完好吗？",
    ),
}


F2_DEFAULT_LINE = "单日飞毛腿需连续3天配送，否则合同会受影响。"


def build_f2_single_utterance(
    step_text: str = "",
    slots: Dict[str, str] | None = None,
    instruction: Any = None,
) -> str:
    """F2 one-shot: use Call Flow step when present; delivery default only as last resort."""
    line = substitute_variables(step_text or "", slots)
    line = _strip_meta_prefix(line)
    if line and not _is_meta_step_line(line):
        merged = re.sub(r"\*+", "", line)
        merged = re.sub(r"^说明", "", merged).strip()
        if not merged.endswith(("。", "！", "？")):
            merged = f"{merged}。"
        if _char_len(merged) <= 32:
            return merged
        compressed = compress_step_to_utterance(
            step_text, slots=slots, current_state="F2", instruction=instruction
        )
        if compressed and compressed not in {"好的，我继续说明。", "嗯，我说下重点。"}:
            return compressed
    if instruction is not None:
        from eval1.layer2.instruction_profile import build_instruction_profile

        if "delivery" not in build_instruction_profile(instruction, slots).active_domains:
            return compress_step_to_utterance(
                step_text, slots=slots, current_state="F2", instruction=instruction
            )
    return F2_DEFAULT_LINE


def pick_flow_step_fallback(
    current_state: str,
    bot_history: List[str] | None = None,
    *,
    attempt: int = 0,
    step_text: str = "",
    slots: Dict[str, str] | None = None,
    instruction: Any = None,
) -> str:
    from eval1.layer2.bot_repeat_guard import pick_non_repeating

    if instruction and current_state.startswith("F"):
        try:
            idx = int(current_state[1:]) - 1
            steps = list(getattr(instruction, "flow_steps", []) or [])
            if 0 <= idx < len(steps):
                line = compress_step_to_utterance(
                    str(steps[idx]),
                    slots=slots,
                    current_state=current_state,
                    instruction=instruction,
                )
                if line and line not in {"好的，我继续说明。", "嗯，我说下重点。"}:
                    return line
        except ValueError:
            pass
    if current_state == "F4":
        if instruction_f4_is_delivery_split(instruction, step_text, slots):
            return build_f4_single_utterance(step_text, slots=slots, instruction=instruction)
        return compress_step_to_utterance(
            step_text,
            slots=slots,
            current_state="F4",
            instruction=instruction,
        )
    alts = list(_FLOW_STATE_ALTS.get(current_state) or ())
    if not alts:
        alts = ["好的，我继续说明。", "嗯，我说下重点。"]
    return pick_non_repeating(alts, list(bot_history or []), attempt=attempt)


def _to_natural_question(step_text: str, slots: Dict[str, str] | None = None) -> str:
    """Extract speakable fragment from step text — no domain-specific templates."""
    _ = slots
    t = _strip_meta_prefix(step_text)
    if _META_NAV_RE.search(t):
        return ""
    t = re.sub(r"^\*+|\*+$", "", t).strip()
    for sep in ("。", "；", ";", "，", ","):
        if sep in t:
            t = t.split(sep)[0].strip()
            break
    return t


def _char_len(text: str) -> int:
    return len((text or "").replace(" ", ""))


def build_f4_single_utterance(
    step_text: str = "",
    slots: Dict[str, str] | None = None,
    instruction: Any = None,
) -> str:
    """F4 one-shot: delivery 3-clause block, or generic step line from instruction."""
    if instruction is not None and not instruction_f4_is_delivery_split(instruction, step_text, slots):
        return compress_step_to_utterance(
            step_text,
            slots=slots,
            current_state="F4",
            instruction=instruction,
        )
    cached = (slots or {}).get("_f4_single")
    if cached:
        return str(cached)
    clauses = _parse_f4_clauses(step_text, slots)
    spoken: List[str] = []
    for clause in clauses[:3]:
        text = substitute_variables(clause or "", slots)
        text = re.sub(r"^说明", "", text).strip()
        if text and not text.endswith(("。", "！", "？", "?", "！")):
            text = f"{text}。"
        if text:
            spoken.append(text)
    if not spoken:
        if instruction_f4_is_delivery_split(instruction, step_text, slots):
            spoken = [f"{c}。" if not c.endswith("。") else c for c in F4_DEFAULT_CLAUSES]
        else:
            return compress_step_to_utterance(step_text, slots=slots, current_state="F4", instruction=instruction)
    return "".join(spoken)


def compress_f4_step_to_utterance(
    step_text: str = "",
    *,
    slots: Dict[str, str] | None = None,
    max_len: int = 30,
) -> str:
    """F4 speakable line; default is full single delivery, compact only when max_len is tight."""
    full = build_f4_single_utterance(step_text, slots=slots)
    if max_len <= 0 or _char_len(full) <= max_len:
        return full
    compact = substitute_variables(F4_COMPRESSED_LINE, slots)
    return compact if _char_len(compact) <= max_len else full


def _raw_is_delivery_f4(raw: str) -> bool:
    return sum(1 for m in _F4_DELIVERY_MARKERS if m in raw) >= 2


def _parse_f4_clauses(step_text: str, slots: Dict[str, str] | None = None) -> List[str]:
    raw = substitute_variables(_strip_meta_prefix(step_text or ""), slots)
    chunks = [c.strip() for c in re.split(r"[。；]", raw) if c.strip()]
    if len(chunks) >= 3:
        return chunks[:3]
    if len(chunks) == 2:
        if _raw_is_delivery_f4(raw):
            return chunks + [F4_DEFAULT_CLAUSES[2]]
        return chunks
    if len(chunks) == 1 and chunks[0]:
        return chunks
    if _raw_is_delivery_f4(raw):
        return list(F4_DEFAULT_CLAUSES)
    return []


def _compress_f4_clause(clause: str, *, slots: Dict[str, str] | None = None, max_len: int = 30) -> str:
    text = substitute_variables(clause or "", slots)
    text = re.sub(r"^说明", "", text).strip()
    text = re.sub(r"^在恶劣天气下工作[、,]?", "恶劣天气", text)
    text = text.replace("按排名进行的", "按排名进行")
    text = text.replace("并非站长干预", "非站长干预")
    text = text.replace("订单量更高", "单量更高")
    text = text.replace("有助于保住飞毛腿资格", "更稳保飞毛腿资格")
    text = re.sub(r"^(骑手应|用户应|需要|必须)", "", text).strip()
    if _char_len(text) > max_len:
        text = text[: max_len - 1]
    return text if text.endswith(("。", "！", "？", "?", "！")) else f"{text}。"


def build_f4_utterance_parts(step_text: str = "", slots: Dict[str, str] | None = None) -> List[str]:
    """F4 三步：排名非站长 / 少拒单取消超时 / 坏天气保资格。"""
    clauses = _parse_f4_clauses(step_text, slots)
    return [_compress_f4_clause(c, slots=slots) for c in clauses[:3]]


def pick_f4_next_utterance(
    bot_state: Dict[str, object] | None,
    step_text: str = "",
    *,
    slots: Dict[str, str] | None = None,
    instruction: Any = None,
) -> str:
    state = bot_state if bot_state is not None else {}
    if int(state.get("f4_speech_index") or 0) >= len(F4_PART_META):
        return ""
    line = str(state.get("f4_single_utterance") or "").strip()
    if not line:
        line = build_f4_single_utterance(step_text, slots=slots, instruction=instruction)
        state["f4_single_utterance"] = line
    return line


def advance_f4_speech_index(bot_state: Dict[str, object] | None) -> None:
    """After bot spoke F4 once, mark all three themes delivered."""
    if bot_state is None:
        return
    bot_state["f4_speech_index"] = len(F4_PART_META)
    bot_state["f4_delivered"] = [key for key, _ in F4_PART_META]
    bot_state["f4_part_index"] = len(F4_PART_META)


def pick_flow_step_utterance(
    current_state: str,
    step_text: str,
    bot_state: Dict[str, object] | None,
    *,
    slots: Dict[str, str] | None = None,
    max_len: int = 30,
    instruction: Any = None,
) -> str:
    """Pick speakable line for a flow step from instruction text."""
    text = step_text
    if (not text or _is_meta_step_line(text)) and instruction and current_state.startswith("F"):
        try:
            idx = int(current_state[1:]) - 1
            steps = list(getattr(instruction, "flow_steps", []) or [])
            if 0 <= idx < len(steps):
                text = str(steps[idx])
        except ValueError:
            pass
    if current_state == "F4":
        if instruction_f4_is_delivery_split(instruction, text, slots):
            return pick_f4_next_utterance(
                bot_state, text, slots=slots, instruction=instruction
            )
        return compress_step_to_utterance(
            text,
            max_len=max_len,
            slots=slots,
            current_state=current_state,
            instruction=instruction,
        )
    if current_state == "F2":
        return build_f2_single_utterance(text, slots=slots, instruction=instruction)
    if str(current_state).startswith("branch::") and instruction:
        from eval1.layer2.step_speakable import resolve_branch_speakable

        spoken = resolve_branch_speakable(instruction, current_state, slots, max_len=max_len)
        if spoken:
            return spoken
    if current_state in {"F3", "F3_RETAIN", "OBJECTION"}:
        return pick_flow_step_fallback(
            current_state,
            attempt=0,
            step_text=text,
            slots=slots,
            instruction=instruction,
        )
    return compress_step_to_utterance(
        text, max_len=max_len, slots=slots, current_state=current_state, instruction=instruction
    )


def f4_parts_remaining(bot_state: Dict[str, object] | None) -> int:
    if not bot_state:
        return 1
    if int(bot_state.get("f4_speech_index") or 0) >= len(F4_PART_META):
        return 0
    return 1


def _f4_part_hit(utterance: str, keywords: tuple[str, ...]) -> bool:
    u = utterance or ""
    return any(k in u for k in keywords)


def f4_utterance_covers_all_parts(utterance: str) -> bool:
    """True when one bot line already contains all three F4 themes."""
    delivered = set()
    for key, kws in F4_PART_META:
        if _f4_part_hit(str(utterance), kws):
            delivered.add(key)
    return len(delivered) >= len(F4_PART_META)


def sync_f4_completion(
    bot_state: Dict[str, object] | None,
    bot_history: List[str] | None = None,
) -> None:
    """Backfill F4 complete flag from prior bot lines (handles state merge gaps)."""
    if bot_state is None:
        return
    if int(bot_state.get("f4_speech_index") or 0) >= len(F4_PART_META):
        return
    candidates = [
        str(bot_state.get("f4_last_utterance") or ""),
        str(bot_state.get("last_bot_utterance") or ""),
    ]
    candidates.extend(reversed(list(bot_history or [])))
    for text in candidates:
        t = text.strip()
        if not t:
            continue
        if f4_utterance_covers_all_parts(t):
            bot_state["f4_last_utterance"] = t
            if not bot_state.get("f4_single_utterance"):
                bot_state["f4_single_utterance"] = t
            advance_f4_speech_index(bot_state)
            return


def pick_f4_post_ack(bot_history: List[str] | None = None, *, attempt: int = 0) -> str:
    from eval1.layer2.bot_repeat_guard import pick_non_repeating

    return pick_non_repeating(list(F4_POST_ACK_ALTS), list(bot_history or []), attempt=attempt)


def update_f4_delivery(bot_state: Dict[str, object] | None, utterance: str) -> None:
    """Mark F4 sub-points delivered based on bot utterance keywords."""
    if bot_state is None:
        return
    delivered = set(bot_state.get("f4_delivered") or [])
    for key, kws in F4_PART_META:
        if _f4_part_hit(str(utterance), kws):
            delivered.add(key)
    bot_state["f4_delivered"] = sorted(delivered)
    if len(delivered) >= len(F4_PART_META):
        bot_state["f4_speech_index"] = len(F4_PART_META)
    idx = int(bot_state.get("f4_speech_index") or 0)
    bot_state["f4_part_index"] = max(idx, min(len(delivered), len(F4_PART_META)))
    bot_state["f4_last_utterance"] = str(utterance)


def f4_coverage_summary(
    bot_state: Dict[str, object] | None,
    bot_history: List[str] | None = None,
) -> Dict[str, object]:
    state = dict(bot_state) if bot_state is not None else {}
    sync_f4_completion(state, bot_history)
    spoken = int(state.get("f4_speech_index") or 0)
    all_keys = [k for k, _ in F4_PART_META]
    delivered = [all_keys[i] for i in range(min(spoken, len(all_keys)))]
    missing = all_keys[spoken:] if spoken < len(all_keys) else []
    last = str(state.get("f4_last_utterance") or state.get("last_bot_utterance") or "")
    entered = bool(state.get("f4_entered")) or spoken > 0 or bool(state.get("f4_parts"))
    return {
        "entered": entered,
        "delivered": delivered,
        "missing": missing,
        "complete": spoken >= len(F4_PART_META),
    }


def compress_step_to_utterance(
    step_text: str,
    max_len: int = 30,
    slots: Dict[str, str] | None = None,
    *,
    current_state: str = "",
    instruction: Any = None,
) -> str:
    """Turn flow step instruction into a speakable bot line."""
    if str(current_state).startswith("branch::") and instruction:
        from eval1.layer2.step_speakable import resolve_branch_speakable

        spoken = resolve_branch_speakable(instruction, current_state, slots, max_len=max_len)
        if spoken:
            return spoken
    text = _strip_meta_prefix(step_text or "")
    if instruction and current_state.startswith("F"):
        try:
            from eval1.layer2.step_speakable import pick_step_speakable, _step_title_needs_script

            idx = int(current_state[1:])
            if _step_title_needs_script(text):
                spoken = pick_step_speakable(
                    instruction, idx, text, slots=slots, max_len=max_len
                )
                if spoken:
                    return spoken
        except ValueError:
            pass
    if not text or _is_meta_step_line(text):
        if instruction and current_state.startswith("F"):
            try:
                idx = int(current_state[1:]) - 1
                steps = list(getattr(instruction, "flow_steps", []) or [])
                if 0 <= idx < len(steps):
                    text = _strip_meta_prefix(str(steps[idx]))
            except ValueError:
                pass
    if not text or _is_meta_step_line(text):
        return pick_flow_step_fallback(
            current_state,
            attempt=0,
            step_text=step_text or text,
            slots=slots,
            instruction=instruction,
        )
    if current_state == "F2":
        return build_f2_single_utterance(text, slots=slots, instruction=instruction)
    if current_state in {"F3", "F3_RETAIN", "OBJECTION"}:
        return pick_flow_step_fallback(
            current_state,
            attempt=0,
            step_text=step_text or text,
            slots=slots,
            instruction=instruction,
        )
    natural = _to_natural_question(text, slots)
    if natural and not _is_meta_step_line(natural):
        text = natural
    elif _is_meta_step_line(text):
        return pick_flow_step_fallback(
            current_state,
            attempt=0,
            step_text=step_text or text,
            slots=slots,
            instruction=instruction,
        )
    for sep in ("。", "；", ";", "，", ","):
        if sep in text:
            text = text.split(sep)[0].strip()
            break
    text = re.sub(r"^(骑手应|用户应|需要|必须)", "", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1] + "。"
    return text if text.endswith(("。", "！", "？", "?", "！")) else f"{text}。"
