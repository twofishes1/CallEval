from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from eval1.layer2.instruction_injection import substitute_variables
from eval1.layer2.persona import PersonaType

# Cross-domain lexicons: terms belonging to a theme. Forbidden = lexicons not active in current instruction.
_DOMAIN_LEXICONS: Dict[str, Tuple[str, ...]] = {
    "delivery": ("配送", "骑手", "接单", "跑单", "飞毛腿", "站长", "派单", "拒单", "上线跑单", "开始配送"),
    "education_live": ("直播", "发课", "低延迟", "标准直播", "培训机构", "校区负责人", "发布页", "课程类型", "带宽"),
    "contract_sales": ("签约", "续费", "合同生效", "名额被占"),
}

_TOPIC_TERM_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}")

# Instruction markdown module titles — must not become user-facing {topic} in shells.
_INSTRUCTION_MODULE_LABELS = frozenset(
    {
        "Role", "Task", "Call", "Flow", "FAQ", "Constraints", "Opening", "Line",
        "Knowledge", "Points", "eval", "mode", "CallFlow",
    }
)

_DOMAIN_TOPIC_DEFAULTS: Dict[str, str] = {
    "delivery": "飞毛腿",
    "education_live": "直播",
    "contract_sales": "合同",
}


@dataclass(frozen=True)
class InstructionProfile:
    """Task-agnostic view derived only from ParsedInstruction + slots."""

    user_role: str
    caller_label: str
    task_summary: str
    role_short: str
    topic_terms: Tuple[str, ...]
    ask_question_seeds: Tuple[str, ...]
    active_domains: Tuple[str, ...]
    forbidden_phrases: Tuple[str, ...]
    off_topic_scope: str
    closing_wish: str
    busy_wish: str


def _first_nonempty(*parts: str) -> str:
    for p in parts:
        t = (p or "").strip()
        if t:
            return t
    return ""


def _instruction_corpus(instruction: Any, slots: Dict[str, str]) -> str:
    parts: List[str] = []
    for attr in ("raw_text", "resolved_text", "role_description", "task_description", "opening_line"):
        text = substitute_variables(str(getattr(instruction, attr, "") or ""), slots)
        if text.strip():
            parts.append(text.strip())
    for step in list(getattr(instruction, "flow_steps", []) or []):
        parts.append(substitute_variables(str(step), slots))
    for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
        parts.append(substitute_variables(str(getattr(kn, "text", kn)), slots))
    for c in list(getattr(instruction, "constraints", []) or []):
        parts.append(substitute_variables(str(getattr(c, "text", c)), slots))
    return "\n".join(parts)


def _score_lexicon(blob: str, terms: Sequence[str]) -> int:
    return sum(1 for t in terms if t in blob)


def infer_active_domains(corpus: str) -> Tuple[str, ...]:
    scores = {name: _score_lexicon(corpus, terms) for name, terms in _DOMAIN_LEXICONS.items()}
    best = max(scores.values()) if scores else 0
    if best <= 0:
        return ()
    active = [name for name, score in scores.items() if score >= max(1, best - 1) and score > 0]
    if not active and best > 0:
        active = [max(scores, key=scores.get)]
    return tuple(active)


def infer_forbidden_phrases(corpus: str, active_domains: Sequence[str]) -> Tuple[str, ...]:
    active = set(active_domains or ())
    forbidden: List[str] = []
    for name, terms in _DOMAIN_LEXICONS.items():
        if name not in active:
            forbidden.extend(terms)
    return tuple(dict.fromkeys(forbidden))


def _infer_caller_label(role_text: str) -> str:
    r = (role_text or "").strip()
    low = r.lower()
    if "站长" in r:
        return "站长"
    if "客服" in r or "customer support" in low or "support specialist" in low:
        return "客服"
    if "specialist" in low or "agent" in low:
        return "客服专员"
    if "销售" in r:
        return "销售"
    if re.search(r"[a-zA-Z]{3,}", r):
        return "客服"
    return "来电方"


def _infer_user_role(role: str, task: str, opening: str) -> str:
    combined = " ".join(x for x in (role, task, opening) if x)
    if opening:
        if re.search(r"机构|校区|培训", opening) and "负责人" in opening:
            return "培训机构/校区负责人"
        if "负责人" in opening:
            return "业务负责人"
        if re.search(r"骑手|配送员", opening):
            return "骑手"
    if "customer support" in role.lower() or "support specialist" in role.lower() or "客服" in role:
        if any(k in task for k in ("机构", "商家", "校区", "培训")):
            return "培训机构/校区负责人"
        return "客户"
    if "站长" in role:
        return "骑手"
    if re.search(r"机构客户|商家|校区|直播|发课", combined):
        return "培训机构/校区负责人"
    if re.search(r"骑手|配送|飞毛腿|跑单", combined):
        return "骑手"
    if "客户" in combined:
        return "客户"
    if "学员" in combined:
        return "学员"
    return "接听电话的用户"


def _role_short(user_role: str) -> str:
    if "负责人" in user_role:
        return "负责人"
    if "骑手" in user_role:
        return "骑手"
    if "客户" in user_role:
        return "客户"
    if "学员" in user_role:
        return "学员"
    return "我"


def _is_bad_topic_term(word: str) -> bool:
    w = (word or "").strip()
    if not w or len(w) < 2:
        return True
    if w in _INSTRUCTION_MODULE_LABELS:
        return True
    if re.fullmatch(r"[A-Za-z]+", w):
        return True
    if w.startswith("你是") or w.startswith("的") or w.endswith("的站长"):
        return True
    return False


def _extract_topic_terms(corpus: str, limit: int = 8) -> Tuple[str, ...]:
    stop = {
        "如果", "然后", "需要", "进行", "可以", "应该", "已经", "是否", "什么", "怎么", "一个", "我们", "你们",
        "对方", "用户", "客户", "负责", "确认", "告知", "说明", "检查", "完成", "开始", "结束", "通话",
        "致电", "通知", "提醒", "他们", "今天", "成功", "签署",
    }
    found: List[str] = []
    for m in _TOPIC_TERM_RE.finditer(corpus):
        w = m.group(0)
        if _is_bad_topic_term(w) or w in stop:
            continue
        if w not in found:
            found.append(w)
        if len(found) >= limit:
            break
    return tuple(found)


def pick_shell_topic(profile: InstructionProfile) -> str:
    """Safe {topic} for last-resort shells — never instruction labels like Role."""
    for domain in profile.active_domains:
        default = _DOMAIN_TOPIC_DEFAULTS.get(domain)
        if default:
            return default
    for term in profile.topic_terms:
        if not _is_bad_topic_term(term):
            return term
    return "这件事"


def _ask_question_seeds(instruction: Any, slots: Dict[str, str], limit: int = 5) -> Tuple[str, ...]:
    seeds: List[str] = []
    for kn in list(getattr(instruction, "knowledge_nodes", []) or [])[:limit]:
        text = substitute_variables(str(getattr(kn, "text", kn)), slots)
        text = re.sub(r"\*\*[^*]+\*\*", "", text).strip()
        if not text:
            continue
        q = text.split("。")[0].split("；")[0][:24]
        if q and q not in seeds:
            seeds.append(q)
    for step in list(getattr(instruction, "flow_steps", []) or [])[:3]:
        text = re.sub(r"\*\*[^*]+\*\*", "", substitute_variables(str(step), slots)).strip()
        if any(k in text for k in ("是否", "吗", "怎么", "如何", "区别")):
            q = text[:28]
            if q not in seeds:
                seeds.append(q)
    return tuple(seeds[:limit])


def _off_topic_scope(user_role: str, task_summary: str, active_domains: Sequence[str]) -> str:
    if "delivery" in active_domains:
        return "配送/跑单日常场景内"
    if "education_live" in active_domains:
        return "机构运营/课程发布场景内"
    blob = user_role + task_summary
    if "机构" in blob or "直播" in blob:
        return "机构运营场景内"
    if "骑手" in blob or "配送" in blob:
        return "配送日常场景内"
    return "当前业务场景边缘"


def _closing_wishes(active_domains: Sequence[str], user_role: str) -> Tuple[str, str]:
    if "education_live" in active_domains:
        return "发课顺利", "工作顺利"
    if "delivery" in active_domains:
        return "配送顺利", "接单顺利"
    if "负责人" in user_role:
        return "工作顺利", "工作顺利"
    return "顺利", "顺利"


def build_instruction_profile(instruction: Any | None, slots: Dict[str, str] | None = None) -> InstructionProfile:
    if instruction is None:
        return InstructionProfile(
            user_role="接听电话的用户",
            caller_label="来电方",
            task_summary="自然回应当前通话内容",
            role_short="我",
            topic_terms=(),
            ask_question_seeds=(),
            active_domains=(),
            forbidden_phrases=(),
            off_topic_scope="当前业务场景边缘",
            closing_wish="顺利",
            busy_wish="顺利",
        )

    slots = dict(slots or {})
    role = _first_nonempty(str(getattr(instruction, "role_description", "") or ""))
    task = substitute_variables(str(getattr(instruction, "task_description", "") or ""), slots)
    opening = substitute_variables(str(getattr(instruction, "opening_line", "") or ""), slots)
    corpus = _instruction_corpus(instruction, slots)

    user_role = _infer_user_role(role, task, opening)
    caller_label = _infer_caller_label(role)
    task_summary = _first_nonempty(task, opening, "自然回应当前通话内容")[:160]
    active = infer_active_domains(corpus)
    forbidden = infer_forbidden_phrases(corpus, active)
    topic_terms = _extract_topic_terms(corpus)
    ask_seeds = _ask_question_seeds(instruction, slots)
    closing_wish, busy_wish = _closing_wishes(active, user_role)

    return InstructionProfile(
        user_role=user_role,
        caller_label=caller_label,
        task_summary=task_summary,
        role_short=_role_short(user_role),
        topic_terms=topic_terms,
        ask_question_seeds=ask_seeds,
        active_domains=active,
        forbidden_phrases=forbidden,
        off_topic_scope=_off_topic_scope(user_role, task_summary, active),
        closing_wish=closing_wish,
        busy_wish=busy_wish,
    )


_PERSONA_SHELLS: Dict[PersonaType, Dict[str, List[str]]] = {
    # 仅 UserSimulatorAgent._shell_fallback 在 LLM+校验重试耗尽后使用；主路径不读此表。
    PersonaType.COOPERATIVE: {
        "comply": ["明白了，知道了。", "好的，我记下了。", "行，我尽量配合。"],
        "confirm": ["明白了，{followup}。", "好的，{followup}。"],
        "reject": ["现在有点忙，稍后再沟通可以吗？", "我先记一下，晚点再确认。"],
        "ask_question": ["{topic}具体是什么意思？", "这个对我有什么影响？"],
        "off_topic": ["对了，{side_question}"],
        "hangup": ["好，先这样，再见。"],
    },
    PersonaType.IMPATIENT: {
        "comply": ["行，{topic}这块知道了。", "好，{topic}记住了，还有吗？"],
        "confirm": ["行了，{followup}。", "行，{topic}知道了，还有吗？"],
        "reject": ["没时间，稍后再说。", "太啰嗦了，先挂。"],
        "ask_question": ["一句话，{topic}啥意思？", "{topic}怎么算？"],
        "off_topic": ["等等，{side_question}"],
        "hangup": ["先挂了，忙。"],
    },
    PersonaType.RESISTANT: {
        "comply": ["行吧，但得看情况。", "知道了，尽量吧，不保证。", "可以了解，但不太想被催。"],
        "confirm": ["嗯，知道了，再说吧。", "行吧，{topic}了解了，但还得看。"],
        "reject": ["这要求有点难接受。", "我们还得再评估一下。"],
        "ask_question": ["依据是什么？", "{topic}谁定的？"],
        "off_topic": ["你们系统怎么老出问题？"],
        "hangup": ["不想聊了，先挂。"],
    },
    PersonaType.QUESTIONING: {
        "comply": ["{topic}这块想再核实下。", "可以，先把{topic}说清楚。"],
        "confirm": ["{topic}怎么算？", "依据是什么？", "拒单太多具体怎么影响？"],
        "reject": ["没讲清影响前我暂不配合。", "还得再想想。"],
        "ask_question": ["{topic}怎么算？", "依据是什么？"],
        "off_topic": ["顺便问，{side_question}"],
        "hangup": ["我再查一下，先挂。"],
    },
    PersonaType.IGNORANT: {
        "comply": ["好像懂了，我试试看。", "嗯，你再说一遍？"],
        "confirm": ["大概明白了。"],
        "reject": ["我没太听懂，先这样吧。", "这个是什么意思？"],
        "ask_question": ["{topic}是啥意思？", "怎么区分？"],
        "off_topic": ["App 上在哪操作？"],
        "hangup": ["我还是不太懂，先挂了。"],
    },
    PersonaType.OFF_TOPIC: {
        "comply": ["行吧，对了{side_question}"],
        "confirm": ["好，我这边还有事。"],
        "reject": ["今天先不处理了。", "我先忙别的。"],
        "ask_question": ["对了，{side_question}"],
        "off_topic": ["顺便问，{side_question}", "你们后台怎么又卡了？"],
        "hangup": ["先挂了，回头再说。"],
    },
}

_GENERIC_MINIMAL: Dict[str, List[str]] = {
    "comply": ["明白了，知道了。", "好的，我记下了。", "行，我尽量配合。"],
    "confirm": ["明白了，先这样。", "好的，我知道了。"],
    "reject": ["现在不太方便，稍后再说。", "我先记一下，晚点确认。"],
    "ask_question": ["这个怎么理解？", "具体有什么影响？", "依据是什么？"],
    "off_topic": ["对了，问个别的事。", "顺便问一句。"],
    "hangup": ["先挂了。", "我有事先挂了。"],
}


def _fill_shell(template: str, profile: InstructionProfile) -> str:
    topic = pick_shell_topic(profile)
    side = profile.ask_question_seeds[0] if profile.ask_question_seeds else "还有别的事吗"
    followup = "我按您说的来" if "负责人" in profile.user_role else "先这样"
    if "education_live" in profile.active_domains:
        followup = "我去发布页看一下"
    elif "delivery" in profile.active_domains:
        followup = "我尽量配合"
    return (
        template.format(role=profile.role_short, topic=topic, side_question=side, followup=followup)
        .replace("。。", "。")
        .strip()
    )


def build_fallback_phrase_pool(
    action: str,
    persona_type: PersonaType,
    profile: InstructionProfile,
) -> List[str]:
    act = action if action in _GENERIC_MINIMAL else "comply"
    shells = list(_PERSONA_SHELLS.get(persona_type, _PERSONA_SHELLS[PersonaType.COOPERATIVE]).get(act, []))
    shells.extend(_GENERIC_MINIMAL.get(act, _GENERIC_MINIMAL["comply"]))
    if act == "ask_question":
        for seed in profile.ask_question_seeds[:4]:
            q = seed if seed.endswith(("？", "?")) else f"{seed}？"
            shells.append(q)
    lines = [_fill_shell(s, profile) for s in shells]
    filtered = [ln for ln in lines if ln and not any(fp in ln for fp in profile.forbidden_phrases)]
    return filtered or [_fill_shell(_GENERIC_MINIMAL[act][0], profile)]


def build_closing_reply_alts_for_profile(profile: InstructionProfile, tone: str) -> List[str]:
    wish = profile.closing_wish
    busy = profile.busy_wish
    if tone in {"busy", "refused"}:
        return [
            "理解，您先忙，再见。",
            f"好的，那祝您{busy}，再见。",
            "明白，这边先挂了，再见。",
        ]
    if tone == "cooperative":
        return [
            f"好的，那就这样，祝您{wish}，再见。",
            "行，辛苦您了，再见。",
            "明白，有问题随时联系，再见。",
            "好的，先这样，再见。",
        ]
    return [
        "行，您先忙，再见。",
        "好的，先这样，有事随时联系，再见。",
        "明白了，那不打扰了，再见。",
    ]
