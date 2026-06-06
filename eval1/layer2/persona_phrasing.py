from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from eval1.layer2.instruction_profile import InstructionProfile, build_instruction_profile, build_fallback_phrase_pool
from eval1.layer2.persona import PersonaCard, PersonaType

# 软引导：描述语气维度，不写可照抄的例句
_PERSONA_TONE = {
    PersonaType.COOPERATIVE: {
        "comply": "友好、积极、愿意配合，语气干脆。",
        "confirm": "确认清楚，可简短致谢。",
        "ask_question": "礼貌追问一个细节。",
        "reject": "极少拒绝；若拒绝也保持礼貌。",
        "off_topic": "几乎不跑题。",
    },
    PersonaType.IMPATIENT: {
        "comply": "短、直、显时间压力；可催对方说重点，但每轮措辞应不同。",
        "confirm": "想快速结束，勿长篇。",
        "ask_question": "只问最关键一点，语气带催促。",
        "reject": "直接说不耐烦、没时间。",
        "off_topic": "偶尔岔话，语气仍急。",
    },
    PersonaType.RESISTANT: {
        "comply": "即使同意也带防备、不情愿或条件。",
        "confirm": "不情不愿地确认。",
        "ask_question": "质疑规则合理性、追问依据。",
        "reject": "明确拒绝或质疑。",
        "off_topic": "借跑题回避。",
    },
    PersonaType.QUESTIONING: {
        "comply": "可先确认，常附带追问依据或后果。",
        "confirm": "确认前再核实细节。",
        "ask_question": "紧扣依据、影响、后果追问。",
        "reject": "因不清楚而暂不配合。",
        "off_topic": "更常追问而非跑题。",
    },
    PersonaType.IGNORANT: {
        "comply": "似懂非懂中同意，常显不确定。",
        "confirm": "确认时仍不太确定。",
        "ask_question": "追问含义、区别、怎么算。",
        "reject": "因听不懂而拖延。",
        "off_topic": "偶尔扯到无关小事。",
    },
    PersonaType.OFF_TOPIC: {
        "comply": "口头同意但易夹带无关话题。",
        "confirm": "确认时顺带提无关事。",
        "ask_question": "问业务时也易岔开。",
        "reject": "用岔话回避。",
        "off_topic": "明显提与当前话题无关的问题。",
    },
}

_UNNATURAL_MARKERS = ("下一项", "下一节点", "Call Flow", "流程节点", "配合推进", "触发节点", "Role", "Task")

_INSTRUCTION_LABEL_RE = re.compile(r"\b(Role|Task|Call\s*Flow|FAQ|Constraints)\b", re.IGNORECASE)

_PERSONA_LABELS = {
    PersonaType.COOPERATIVE: "配合型",
    PersonaType.IMPATIENT: "急躁型",
    PersonaType.RESISTANT: "抵抗型",
    PersonaType.QUESTIONING: "质疑型",
    PersonaType.IGNORANT: "懵懂型",
    PersonaType.OFF_TOPIC: "跑题型",
}

# 仅标记完全通用的兜底句，指令动态生成的句子不算 canned
_GENERIC_CANNED = frozenset(
    {
        "行，我先了解一下。",
        "行，我先听一下。",
        "可以，您继续说。",
        "好的，您继续说。",
        "好，我听一下。",
        "明白了，先这样。",
        "好的，我知道了。",
        "现在不太方便，稍后再说。",
        "我先记一下，晚点确认。",
        "这个怎么理解？",
        "具体有什么影响？",
        "依据是什么？",
        "对了，问个别的事。",
        "顺便问一句。",
        "先挂了。",
        "我有事先挂了。",
    }
)

# 用户身份/对方身份词，不可作「行，{词}我明白了」的回声
_ROLE_ECHO_BLOCKLIST = frozenset(
    {
        "骑手",
        "配送员",
        "负责人",
        "客户",
        "学员",
        "站长",
        "来电方",
        "机构",
        "校区",
        "培训",
    }
)

_HOLLOW_EXACT = frozenset(
    {
        "好", "嗯", "行", "成", "好。", "嗯。", "行。", "成。", "哦", "哦。",
        "明白", "明白。", "知道了", "知道了。", "了解了", "了解了。", "好嗯",
    }
)

_COMPLY_MARKERS = ("没问题", "可以开始", "马上", "开始配送", "能配送", "愿意配合")

_RESISTANT_WARM_COOPERATIVE = (
    "好的，", "好的,", "明白了", "知道了", "我尽量配合", "会小心的", "尽量上线", "记下了", "谢谢站长", "没问题", "一定",
)


def _resolve_persona_type(persona: Union[PersonaCard, PersonaType, str, None]) -> PersonaType:
    if isinstance(persona, PersonaType):
        return persona
    if isinstance(persona, PersonaCard):
        return persona.persona_type
    if isinstance(persona, str):
        try:
            return PersonaType(persona)
        except ValueError:
            pass
    return PersonaType.COOPERATIVE


def _profile(
    instruction: object | None,
    slot_values: Optional[Dict[str, str]],
    forbidden_phrases: tuple[str, ...] | list[str] | None,
) -> InstructionProfile:
    profile = build_instruction_profile(instruction, slot_values)
    if forbidden_phrases:
        merged = tuple(dict.fromkeys([*profile.forbidden_phrases, *[str(x) for x in forbidden_phrases if x]]))
        return InstructionProfile(
            user_role=profile.user_role,
            caller_label=profile.caller_label,
            task_summary=profile.task_summary,
            role_short=profile.role_short,
            topic_terms=profile.topic_terms,
            ask_question_seeds=profile.ask_question_seeds,
            active_domains=profile.active_domains,
            forbidden_phrases=merged,
            off_topic_scope=profile.off_topic_scope,
            closing_wish=profile.closing_wish,
            busy_wish=profile.busy_wish,
        )
    return profile


def is_instruction_label_leak(utterance: str) -> bool:
    """User line leaked instruction module label (e.g. Role from # Role header)."""
    u = (utterance or "").strip()
    if not u:
        return False
    return bool(_INSTRUCTION_LABEL_RE.search(u))


def is_role_term_misuse(utterance: str, profile: InstructionProfile) -> bool:
    """User echoed their own role label awkwardly, e.g. 「骑手我明白了」."""
    u = (utterance or "").strip()
    if not u:
        return False
    role = profile.role_short
    if role and role != "我" and f"{role}我" in u.replace(" ", ""):
        return True
    for block in _ROLE_ECHO_BLOCKLIST:
        if re.search(rf"行[，,]?{re.escape(block)}我(明白|知道|了解)", u):
            return True
    return False


def is_listen_only_ack(utterance: str, last_bot_utterance: str, *, action: str = "") -> bool:
    """「先听一下/您继续说」在对方已说完要点时不像真人确认。"""
    u = (utterance or "").strip().rstrip("。！？?!")
    bot = (last_bot_utterance or "").strip()
    if not bot or len(bot) < 12:
        return False
    if not any(k in u for k in ("听一下", "先听", "您继续说", "我先了解", "听您说")):
        return False
    if action == "confirm":
        return True
    return len(bot) >= 18


def is_canned_minimal_utterance(utterance: str) -> bool:
    u = (utterance or "").strip()
    return bool(u) and u in _GENERIC_CANNED


def _pool_for_action(
    action: str,
    persona: Union[PersonaCard, PersonaType, str, None],
    *,
    profile: InstructionProfile,
) -> List[str]:
    ptype = _resolve_persona_type(persona)
    return build_fallback_phrase_pool(action, ptype, profile)


def _echoable_terms(bot: str, profile: InstructionProfile) -> List[str]:
    """Substantive terms from bot line — exclude user/caller role labels."""
    block = set(_ROLE_ECHO_BLOCKLIST)
    block.add(profile.role_short)
    for part in re.split(r"[/、，,]", profile.user_role):
        block.add(part.strip())
    block.add(profile.caller_label)
    out: List[str] = []
    for term in profile.topic_terms:
        if term in block or len(term) < 2:
            continue
        if term in bot and term not in out:
            out.append(term)
    if not out:
        for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", bot):
            w = m.group(0)
            if w in block or w in out:
                continue
            if w in ("今天", "已经", "可以", "需要", "否则", "有效", "完成"):
                continue
            out.append(w)
            if len(out) >= 2:
                break
    return out


def _persona_f4_confirm_lines(
    persona: Union[PersonaCard, PersonaType, str, None],
    bot: str,
) -> List[str]:
    """Persona-toned F4 confirm examples (shell fallback / pool boost only)."""
    ptype = _resolve_persona_type(persona)
    if not any(m in bot for m in _F4_ECHO_MARKERS):
        return []
    if ptype == PersonaType.IMPATIENT:
        return [
            "行，排名拒单记住了，还有吗？",
            "知道了，坏天气也会跑，快说完吧。",
            "行，少拒单别超时，行了没？",
        ]
    if ptype == PersonaType.QUESTIONING:
        return [
            "排名是系统自动算的吧？",
            "恶劣天气也算进资格吗？",
            "拒单太多具体怎么影响排名？",
        ]
    if ptype == PersonaType.RESISTANT:
        return [
            "行吧，排名这套我了解了。",
            "知道了，但拒单那块还得看情况。",
        ]
    if ptype == PersonaType.IGNORANT:
        return [
            "排名是怎么算的，再说一遍？",
            "恶劣天气也算吗？",
        ]
    return [
        "明白了，排名和拒单我会注意。",
        "好的，恶劣天气我也尽量上线。",
    ]


def _context_boost_lines(
    action: str,
    last_bot_utterance: str,
    profile: InstructionProfile,
    *,
    persona: Union[PersonaCard, PersonaType, str, None] = None,
) -> List[str]:
    bot = (last_bot_utterance or "").strip()
    if not bot:
        return []
    extra: List[str] = []
    if action == "comply" and any(k in bot for k in ("负责人", "是您", "请问您")):
        if not any(k in bot for k in ("升级", "低延迟", "标准直播", "发课")):
            extra.extend(["是的，我是。", "对，是我。", "嗯，我负责这块。"])
    if action == "comply" and any(k in bot for k in ("升级", "低延迟", "标准直播", "发课", "选项")):
        extra.extend(["好的，知道了。", "明白，您继续说。", "嗯，了解了。"])
    if action in {"comply", "confirm"} and "delivery" in profile.active_domains:
        ptype = _resolve_persona_type(persona)
        if any(k in bot for k in ("连续", "3天", "三天", "合同")):
            if ptype == PersonaType.RESISTANT:
                extra.extend(["行吧，尽量连续跑，但不一定每天够。", "知道了，3天我试试，可得看情况。"])
            else:
                extra.extend(["连续三天配送，明白了。", "行，我会尽量连续跑满。"])
        if any(k in bot for k in ("安全", "辛苦", "注意")):
            if ptype == PersonaType.RESISTANT:
                extra.extend(["行吧，会注意，但别催太紧。", "知道了，路上小心，不过也看情况。"])
            else:
                extra.extend(["谢谢站长，会注意安全的。", "好的，路上会小心的。"])
        if any(k in bot for k in ("排名", "拒单", "超时", "天气", "资格")):
            extra.extend(_persona_f4_confirm_lines(persona, bot))
            if action != "confirm" and ptype != PersonaType.RESISTANT:
                extra.extend(
                    [
                        "明白了，排名和拒单我会注意。",
                        "好的，恶劣天气我也尽量上线。",
                        "行，少拒单、别超时我记住了。",
                    ]
                )
    corpus = profile.task_summary + " ".join(profile.topic_terms) + " ".join(profile.ask_question_seeds)
    for term in _echoable_terms(bot, profile):
        if action == "reject":
            extra.append(f"关于{term}，我还需要再想想。")
        elif action == "ask_question":
            extra.append(f"{term}具体怎么算？")
        elif action == "comply":
            if _resolve_persona_type(persona) == PersonaType.RESISTANT:
                extra.append(f"行吧，{term}知道了，但还得看情况。")
            else:
                extra.append(f"行，{term}这块我明白了。")
        elif action == "confirm":
            if _resolve_persona_type(persona) == PersonaType.RESISTANT:
                extra.append(f"行吧，{term}我了解了，再说吧。")
            else:
                extra.append(f"好的，{term}我记住了。")
    for m in re.finditer(r"[\u4e00-\u9fff]{2,4}", bot):
        w = m.group(0)
        if w in corpus and action == "reject":
            extra.append(f"关于{w}，我还需要再想想。")
    for seed in profile.ask_question_seeds:
        if action != "ask_question":
            continue
        if any(w in bot for w in re.findall(r"[\u4e00-\u9fff]{2,4}", seed)[:2]):
            q = seed if seed.endswith(("？", "?")) else f"{seed}？"
            extra.append(q)
    filtered = [ln for ln in extra if not any(fp in ln for fp in profile.forbidden_phrases)]
    return list(dict.fromkeys(filtered))


def _rank_pool_by_context(pool: List[str], last_bot_utterance: str, profile: InstructionProfile) -> List[str]:
    bot = (last_bot_utterance or "").strip()
    if not bot:
        return pool
    cues = [t for t in profile.topic_terms if t in bot]
    cues.extend(re.findall(r"[\u4e00-\u9fff]{2,6}", bot)[:6])
    cues = list(dict.fromkeys(cues))
    if not cues:
        return pool
    return sorted(pool, key=lambda line: sum(1 for c in cues if c in line), reverse=True)


def get_persona_tone_for_action(persona: PersonaCard, action: str) -> str:
    tones = _PERSONA_TONE.get(persona.persona_type, _PERSONA_TONE[PersonaType.COOPERATIVE])
    return tones.get(action, tones.get("comply", "自然口语回应。"))


def get_persona_voice_guide(persona: PersonaCard) -> str:
    label = _PERSONA_LABELS.get(persona.persona_type, persona.persona_type.value)
    traits = "、".join(persona.utterance_patterns or []) or "自然口语"
    return (
        f"【{label}·语气软约束】{persona.system_prompt_fragment}\n"
        f"情绪：{persona.emotion_description}\n"
        f"表达特征：{traits}\n"
        "注意：以上只约束怎么说，不约束具体原话；每轮自主措辞，禁止复读固定句式或模板句。"
    )


def enrich_path_utterance_hint(action: str, base_hint: str, *, next_node: str = "") -> str:
    from eval1.layer2.path_user_driver import path_action_label

    parts = [f"路径动作：{path_action_label(action)}"]
    if base_hint:
        parts.append(base_hint)
    if next_node:
        parts.append(f"目标节点 {next_node}")
    parts.append("（只约束动作类型，不规定具体台词；须先承接对方上一句要点，再体现动作；勿用套路句）")
    return "；".join(parts)


def build_minimal_action_utterance(
    action: str,
    *,
    turn: int = 0,
    user_history: Optional[List[str]] = None,
    persona: Union[PersonaCard, PersonaType, str, None] = None,
    last_bot_utterance: str = "",
    instruction: object | None = None,
    slot_values: Optional[Dict[str, str]] = None,
    forbidden_phrases: tuple[str, ...] | list[str] | None = None,
    **_ignored: object,
) -> str:
    """Last-resort phrase from _PERSONA_SHELLS; normal turns use LLM in UserSimulatorAgent."""
    profile = _profile(instruction, slot_values, forbidden_phrases)
    pool = _pool_for_action(action, persona, profile=profile)
    boost = _context_boost_lines(action, last_bot_utterance, profile, persona=persona)
    bot = (last_bot_utterance or "").strip()
    f4_confirm = action == "confirm" and any(m in bot for m in _F4_ECHO_MARKERS)
    if f4_confirm:
        pins = _persona_f4_confirm_lines(persona, bot)
        pool = pins + [b for b in boost if b not in pins] + pool
    else:
        pool = boost + pool
        pool = _rank_pool_by_context(pool, last_bot_utterance, profile)
    history = list(user_history or [])
    for i in range(len(pool)):
        line = pool[(turn + i) % len(pool)]
        if line not in history:
            return line
    return pool[turn % len(pool)] if pool else "好的，我知道了。"


build_persona_action_utterance = build_minimal_action_utterance


def verify_persona_tone(utterance: str, persona: PersonaCard, *, sampled_action: str) -> bool:
    u = (utterance or "").strip()
    if not u:
        return False
    if any(m in u for m in _UNNATURAL_MARKERS):
        return False
    if sampled_action == "reject" and any(m in u for m in _COMPLY_MARKERS):
        return False
    if is_resistant_overly_cooperative(u, persona, action=sampled_action):
        return False
    return True


def is_resistant_overly_cooperative(
    utterance: str,
    persona: PersonaCard,
    *,
    action: str = "",
) -> bool:
    """抵触型 comply/confirm：可推进但须带勉强/保留，禁止热情配合腔。"""
    if persona.persona_type != PersonaType.RESISTANT:
        return False
    if action not in {"comply", "confirm"}:
        return False
    u = (utterance or "").strip().rstrip("。！？?!")
    if not u:
        return True
    if _resistant_has_reluctant_tone(u):
        return False
    if any(w in u for w in _RESISTANT_WARM_COOPERATIVE):
        return True
    if u.startswith("好的"):
        return True
    return True


def _resistant_has_reluctant_tone(u: str) -> bool:
    if any(m in u for m in ("但", "不太", "得看", "行吧", "再说", "未必", "不一定", "难", "顾虑", "凭什么")):
        return True
    if ("尽量" in u or "尽力" in u) and not u.startswith("好的"):
        return True
    if ("？" in u or "?" in u) and any(k in u for k in ("咋", "怎么", "啥", "吗", "咋办", "凭什么")):
        return True
    return False


_GENERIC_PERSONA_STUBS = frozenset(
    {
        "行，说重点。",
        "行，说重点",
        "大体明白，但还想确认一点。",
        "大体明白，但还想确认一点",
        "可以，先把规则说清楚。",
        "嗯，还有吗？",
        "好，接着说。",
    }
)

_F4_ECHO_MARKERS = ("排名", "拒单", "取消", "超时", "天气", "资格", "站长", "飞毛腿", "派单")


def is_f4_bot_context(last_bot_utterance: str) -> bool:
    bot = (last_bot_utterance or "").strip()
    return any(m in bot for m in _F4_ECHO_MARKERS)


def is_generic_persona_stub(
    utterance: str,
    last_bot_utterance: str,
    *,
    action: str = "",
) -> bool:
    """Persona 套话未承接 Bot 刚说的业务要点（如 F4 后「说重点/还想确认一点」）。"""
    u = (utterance or "").strip().rstrip("。！？?!")
    bot = (last_bot_utterance or "").strip()
    if u in _GENERIC_PERSONA_STUBS or f"{u}。" in _GENERIC_PERSONA_STUBS:
        return True
    f4_context = any(m in bot for m in _F4_ECHO_MARKERS)
    if not f4_context:
        return False
    hollow_confirm = (
        "还想确认" in u
        or "说重点" in u
        or u in {"大体明白", "明白了", "知道了"}
        or (u.startswith("行") and len(u) <= 8 and not any(m in u for m in _F4_ECHO_MARKERS))
    )
    if action == "confirm" and hollow_confirm:
        return True
    if action == "confirm" and not any(m in u for m in _F4_ECHO_MARKERS):
        if any(k in u for k in ("明白", "知道", "大体", "确认一点", "说重点", "还有吗", "再想想", "核实下")):
            return True
    return False


def is_impatient_hollow_response(
    utterance: str,
    last_bot_utterance: str,
    persona: PersonaCard,
    *,
    action: str = "",
) -> bool:
    """急躁型用了中性套话，未体现催促或未承接 Bot 要点。"""
    if persona.persona_type != PersonaType.IMPATIENT:
        return False
    u = (utterance or "").strip().rstrip("。！？?!")
    bot = (last_bot_utterance or "").strip()
    bland = {
        "嗯，还有别的吗",
        "还有别的事吗",
        "对了，问个别的事",
        "好的，我记下了",
        "明白了，知道了",
    }
    if u in bland or f"{u}。" in {f"{b}。" for b in bland}:
        return True
    if "还有别的" in u and bot and len(bot) >= 12:
        stop = frozenset({"好的", "现在", "我们", "这个", "一下", "骑手", "站长"})
        topics = [t for t in re.findall(r"[\u4e00-\u9fff]{2,}", bot) if t not in stop]
        if topics and not any(t in u for t in topics[:6]):
            return True
    if action == "confirm" and is_f4_bot_context(bot):
        if not any(m in u for m in _F4_ECHO_MARKERS) and any(k in u for k in ("好的", "明白", "尽量", "知道了")):
            return True
    return False


def is_questioning_hollow_confirm(
    utterance: str,
    last_bot_utterance: str,
    persona: PersonaCard,
    *,
    action: str = "",
) -> bool:
    """质疑型 F4 收口：须点出规则词或带具体问句，禁止空泛「还想确认一点」。"""
    if persona.persona_type != PersonaType.QUESTIONING or action != "confirm":
        return False
    if not is_f4_bot_context(last_bot_utterance):
        return False
    u = (utterance or "").strip()
    if any(m in u for m in _F4_ECHO_MARKERS):
        return False
    if any(k in u for k in ("还想确认", "大体明白", "核实下", "再想想", "确认一点")):
        return True
    if ("？" not in u and "?" not in u) and any(k in u for k in ("明白", "知道", "好的", "行")):
        return True
    return False


def is_disconnected_user_response(utterance: str, last_bot_utterance: str) -> bool:
    """User generic ack without any echo of bot's topic — '各说各话'."""
    u = (utterance or "").strip().rstrip("。！？?!")
    bot = (last_bot_utterance or "").strip()
    if not bot or len(bot) < 10:
        return False
    if any(k in u for k in ("听一下", "先听", "您继续说", "我先了解", "说重点", "还想确认")):
        return True
    if len(u) > 28:
        return False
    ack_markers = ("好的", "可以", "明白", "知道", "继续", "试用", "试一下", "嗯", "听", "行")
    if not any(g in u for g in ack_markers):
        return False
    stop = frozenset(
        {"好的", "现在", "我们", "这个", "一下", "您是通过", "请问", "麻烦", "稍后", "已经", "可以", "骑手"}
    )
    topics = [t for t in re.findall(r"[\u4e00-\u9fff]{2,}", bot) if t not in stop]
    if not topics:
        return False
    return not any(t in u for t in topics[:8])


def is_hollow_user_response(utterance: str, persona: PersonaCard) -> bool:
    u = (utterance or "").strip()
    if not u:
        return True
    core = u.rstrip("。！？?!")
    if persona.persona_type == PersonaType.IMPATIENT:
        return not core
    if u in _HOLLOW_EXACT or core in _HOLLOW_EXACT:
        return True
    if len(core) <= 2:
        return True
    if core in {"好的", "好吧", "好嘞", "嗯嗯", "行吧"} and persona.persona_type not in {
        PersonaType.COOPERATIVE,
    }:
        return True
    return False


def build_persona_contextual_tone_hint(
    persona: PersonaCard,
    *,
    action: str,
    current_state: str,
    last_bot_utterance: str = "",
) -> str:
    """LLM soft guide: persona tone + must echo bot context (not fixed lines to copy)."""
    bot = (last_bot_utterance or "").strip()
    f4_ctx = any(m in bot for m in _F4_ECHO_MARKERS)
    p = persona.persona_type

    if action == "confirm" and (current_state == "F4" or f4_ctx):
        tone_map = {
            PersonaType.IMPATIENT: (
                "【语气·急躁型·F4收口】句短≤14字、可催促，但必须点到排名/拒单/天气/超时之一；"
                "如「行，排名知道了，还有吗？」——禁止无关键词的「说重点」。"
            ),
            PersonaType.QUESTIONING: (
                "【语气·质疑型·F4收口】须含具体规则词追问或确认，"
                "如「排名是系统算的吧？」——禁止空泛「还想确认一点」。"
            ),
            PersonaType.RESISTANT: (
                "【语气·抵触型·F4收口】可带「行吧/但」，仍须提到排名或拒单等要点。"
            ),
            PersonaType.IGNORANT: (
                "【语气·懵懂型·F4收口】针对排名/拒单/天气追问「怎么算/什么意思」。"
            ),
            PersonaType.COOPERATIVE: (
                "【语气·配合型·F4收口】友好简短，点出排名/拒单/天气至少一项。"
            ),
            PersonaType.OFF_TOPIC: (
                "【语气·跑题型·F4收口】先简短确认规则一点，可夹半句弱相关岔话。"
            ),
        }
        return tone_map.get(p, tone_map[PersonaType.COOPERATIVE])

    if p == PersonaType.RESISTANT and action in {"comply", "confirm"} and bot:
        return (
            "【语气·抵触型·配合】动作上可同意推进，但须带勉强/保留："
            "用「行吧/但/得看情况/不一定/尽量试试」等，且先点出对方刚说的关键词；"
            "禁止热情「好的，明白了/会小心的/尽量配合/尽量上线」。"
        )

    if p == PersonaType.IMPATIENT and action in {"comply", "confirm"} and bot:
        return (
            "【语气·急躁型】短句、催促感；须先接住对方刚说的关键词再表态，"
            "勿空泛「说重点/还有吗」而不提内容。"
        )
    if p == PersonaType.QUESTIONING and action in {"comply", "confirm", "ask_question"} and bot:
        return "【语气·质疑型】须体现追问或核实，且要指向对方刚说的具体信息。"
    return ""


def build_persona_interest_hint(
    persona: PersonaCard,
    *,
    action: str,
    current_state: str,
    last_bot_utterance: str = "",
) -> str:
    bot = (last_bot_utterance or "").strip()
    rule_cue = bool(re.search(r"[\u4e00-\u9fff]{2,}", bot))
    f4_in_bot = any(m in bot for m in _F4_ECHO_MARKERS)
    if action == "confirm" and (current_state == "F4" or f4_in_bot):
        return (
            "【F4确认·必达】对方刚说明排名/拒单/天气等规则，须至少点出其中一项再表示理解并准备结束；"
            "禁止空泛「还想确认一点/说重点/您继续说」而不提具体内容。"
        )
    if persona.persona_type == PersonaType.QUESTIONING:
        if action == "confirm" and rule_cue:
            return (
                "【兴趣点·质疑型·收口】若仍有疑问，须针对对方刚说的具体规则追问一句（含关键词）；"
                "否则简短确认已理解，勿只说「还想确认一点」。"
            )
        if action in {"ask_question", "comply"} and rule_cue:
            return (
                "【兴趣点·质疑型】对方刚提到规则/数字/后果，你若没完全听懂，"
                "本轮应带一点追问或核实（依据、怎么算、不做到会怎样），不要只敷衍确认。"
            )
        return "【兴趣点·质疑型】保持谨慎，必要时追问一句，不要无思考地全盘接受。"
    if persona.persona_type == PersonaType.RESISTANT:
        if rule_cue:
            return (
                "【兴趣点·抵触型】对强制类要求可表达顾虑、条件或不情愿，"
                "勿热情配合；措辞须符合抵触型，勿用配合型套话。"
            )
        return "【兴趣点·抵触型】即使同意也要带「但/不太/得看情况」类保留态度。"
    if persona.persona_type == PersonaType.COOPERATIVE:
        if action == "reject":
            return "【兴趣点·配合型】若需表达困难，用礼貌、具体的原因，勿用「规则苛刻」类抵触腔。"
        if rule_cue and action in {"comply", "confirm", "ask_question"}:
            return (
                "【兴趣点·配合型】友好干脆，但须点出对方刚提到的具体内容（规则/选项/费用等）再表态，"
                "禁止空泛「好的/您继续说」。"
            )
        return "【兴趣点·配合型】信息清楚就简短确认并推进，措辞每轮要有变化。"
    if persona.persona_type == PersonaType.IMPATIENT:
        if action == "confirm" and f4_in_bot:
            return "【兴趣点·急躁型·收口】短句确认排名/拒单/天气至少一点，勿再说「说重点」（对方已说完）。"
        return "【兴趣点·急躁型】少客套，抓结果；若对方尚未说清可催重点，句长宜短。"
    if persona.persona_type == PersonaType.IGNORANT:
        if rule_cue:
            return "【兴趣点·懵懂型】听不太懂时追问「什么意思/怎么算」，不要装懂只回好/嗯。"
        return "【兴趣点·懵懂型】不确定就直说没听懂，请对方解释。"
    if persona.persona_type == PersonaType.OFF_TOPIC:
        return "【兴趣点·跑题型】可夹带一句与当前规则弱相关的话，但别完全脱离业务。"
    return ""
