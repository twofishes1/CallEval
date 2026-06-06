from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from eval1.config import settings

ACTION_KEYWORDS = {
    "reject": [
        "不想",
        "不太想",
        "不想签",
        "不签",
        "先不签",
        "先不",
        "不想参加",
        "不想办",
        "拒绝",
        "不合理",
        "苛刻",
        "谁定",
        "没必要",
        "不接受",
        "算了",
        "不太想签",
        "做不到",
        "太难",
        "不行",
        "不能",
        "没空",
        "没时间",
        "别找",
        "别说了",
        "不说了",
        "不接",
        "忙呢",
        "忙着",
    ],
    "ask_question": [
        "？",
        "?",
        "吗",
        "什么",
        "为什么",
        "依据",
        "怎么",
        "哪",
        "几点",
        "多少",
        "几天",
        "几单",
        "什么意思",
    ],
    "comply": [
        "可以",
        "好的",
        "明白",
        "知道了",
        "试试",
        "行吧",
        "签",
        "能跑",
        "马上",
        "开始",
        "配送",
        "上线",
        "执行",
        "确认",
        "没问题",
        "继续",
        "行",
        "好",
        "嗯",
        "成",
    ],
    "confirm": [
        "确认",
        "就这样",
        "按这个",
        "知道了谢谢",
        "可以了",
    ],
    "off_topic": [
        "顺便",
        "对了",
        "下雨",
        "头盔",
        "煎饼",
        "范围",
        "修路",
        "奶茶",
        "工资",
        "结算",
        "app",
        "平台",
        "投诉",
        "合同状态",
        "哪里看",
        "在哪看",
        "怎么查",
        "界面",
    ],
    "hangup": ["挂了", "再见", "先挂", "拜拜"],
}

ACKNOWLEDGMENT_MARKERS = (
    "谢谢",
    "感谢",
    "收到",
    "尽量",
    "接单",
    "多接",
    "记下",
    "会的",
    "好嘞",
    "配合",
    "多跑",
    "注意安全",
)

REAL_QUESTION_MARKERS = (
    "什么",
    "为什么",
    "怎么",
    "依据",
    "多少",
    "几天",
    "几单",
    "什么意思",
    "哪",
    "几点",
)

OOB_SCOPE_MARKERS = (
    "app",
    "App",
    "APP",
    "合同状态",
    "哪里看",
    "在哪看",
    "怎么查",
    "界面",
    "入口",
    "设置",
    "工资",
    "结算",
    "投诉",
    "头盔",
    "煎饼",
    "修路",
    "奶茶",
)

RETAIN_SUCCESS_MARKERS = [
    "行吧",
    "好吧",
    "试试",
    "我试试",
    "先试试",
    "勉强",
    "可以吧",
    "签就签",
    "先送",
    "知道了",
    "明白了",
]

FSM_ACTIONS = frozenset({"comply", "reject", "ask_question", "off_topic", "hangup", "confirm", "unknown"})


def is_oob_scope_question(utterance: str) -> bool:
    """Questions outside call script scope (App UI, ops, unrelated topics)."""
    u = (utterance or "").strip().lower()
    if not u:
        return False
    raw = utterance or ""
    if any(k in raw for k in OOB_SCOPE_MARKERS):
        return True
    if any(k in u for k in ("app", "平台")) and any(k in raw for k in REAL_QUESTION_MARKERS):
        return True
    return False


@dataclass
class ActionResult:
    """Single authoritative FSM action signal."""

    action: str
    confidence: float
    source: str = "keyword"
    needs_review: bool = False
    retain_success: bool = False
    raw_utterance: str = ""

    def to_fsm_action(self) -> str:
        return self.action if self.action in FSM_ACTIONS else "unknown"


def is_retain_success(utterance: str) -> bool:
    u = (utterance or "").strip()
    if not u:
        return False
    if any(k in u for k in ACTION_KEYWORDS["reject"]):
        return False
    return any(k in u for k in RETAIN_SUCCESS_MARKERS)


def looks_like_acknowledgment(utterance: str) -> bool:
    """User accepted / thanked / will comply — should advance FSM, not hold."""
    u = (utterance or "").strip()
    if len(u) < 2:
        return False
    if any(k in u for k in ACTION_KEYWORDS["reject"]):
        return False
    if any(k in u for k in REAL_QUESTION_MARKERS):
        return False
    if any(k in u for k in ("？", "?")) and any(k in u for k in REAL_QUESTION_MARKERS + ("吗",)):
        if any(k in u for k in REAL_QUESTION_MARKERS):
            return False
    if any(k in u for k in ACTION_KEYWORDS["comply"]):
        return True
    return any(k in u for k in ACKNOWLEDGMENT_MARKERS)


def split_knowledge_snippets(text: str, max_items: int = 3) -> List[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"[。；;！!？?]", raw)
    out: List[str] = []
    for p in parts:
        s = p.strip()
        if len(s) >= 4:
            out.append(s[:40])
        if len(out) >= max_items:
            break
    return out


def detect_actual_action(utterance: str, *, default: str = "comply") -> str:
    """Backward-compatible sync helper."""
    result = ActionDetector().detect_sync(utterance, default=default)
    if result.action == "unknown":
        return default
    return result.action


class ActionDetector:
    """
    Single authoritative FSM action detector.
    Layer 1: keyword rules (fast)
    Layer 2: optional LLM classify (async, fuzzy)
    Layer 3: UNKNOWN when uncertain — never guess for FSM
    """

    KEYWORD_CONFIDENCE = 0.85
    LLM_MIN_CONFIDENCE = 0.60

    def detect_sync(self, utterance: str, *, default: str = "") -> ActionResult:
        u = (utterance or "").strip()
        if not u:
            return ActionResult(
                action="unknown",
                confidence=0.0,
                source="empty",
                needs_review=True,
                raw_utterance=u,
            )
        kw = self._keyword_match(u)
        if kw.confidence >= self.KEYWORD_CONFIDENCE:
            kw.retain_success = is_retain_success(u)
            return kw
        if kw.action != "unknown" and kw.confidence >= 0.55:
            kw.retain_success = is_retain_success(u)
            kw.needs_review = kw.confidence < self.KEYWORD_CONFIDENCE
            return kw
        if default and default in FSM_ACTIONS - {"unknown"}:
            return ActionResult(
                action=default,
                confidence=0.45,
                source="default",
                needs_review=True,
                retain_success=is_retain_success(u),
                raw_utterance=u,
            )
        return ActionResult(
            action="unknown",
            confidence=kw.confidence,
            source="unknown",
            needs_review=True,
            retain_success=is_retain_success(u),
            raw_utterance=u,
        )

    async def detect(
        self,
        utterance: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        default: str = "",
    ) -> ActionResult:
        u = (utterance or "").strip()
        if not u:
            return ActionResult(
                action="unknown",
                confidence=0.0,
                source="empty",
                needs_review=True,
                raw_utterance=u,
            )

        kw = self._keyword_match(u)
        if kw.confidence >= self.KEYWORD_CONFIDENCE:
            kw.retain_success = is_retain_success(u)
            return kw

        if bool(getattr(settings, "action_llm_fallback", False)) and kw.confidence < self.KEYWORD_CONFIDENCE:
            llm = await self._llm_classify(u, context=context or {})
            if llm.confidence >= self.LLM_MIN_CONFIDENCE and llm.action != "unknown":
                llm.retain_success = is_retain_success(u)
                return llm

        if kw.action != "unknown" and kw.confidence >= 0.55:
            kw.retain_success = is_retain_success(u)
            kw.needs_review = kw.confidence < self.KEYWORD_CONFIDENCE
            return kw

        path_hint = str((context or {}).get("path_hint") or "")
        fallback = default or (path_hint if path_hint in FSM_ACTIONS else "")
        if fallback and fallback in FSM_ACTIONS - {"unknown"}:
            return ActionResult(
                action=fallback,
                confidence=0.5,
                source="path_hint",
                needs_review=True,
                retain_success=is_retain_success(u),
                raw_utterance=u,
            )

        return ActionResult(
            action="unknown",
            confidence=kw.confidence,
            source="unknown",
            needs_review=True,
            retain_success=is_retain_success(u),
            raw_utterance=u,
        )

    def _keyword_match(self, utterance: str) -> ActionResult:
        u = utterance
        if any(k in u for k in ACTION_KEYWORDS["hangup"]):
            return ActionResult("hangup", 0.95, "keyword", raw_utterance=u)
        if any(k in u for k in ACTION_KEYWORDS["reject"]):
            return ActionResult("reject", 0.92, "keyword", raw_utterance=u)

        has_comply = any(k in u for k in ACTION_KEYWORDS["comply"])
        has_confirm = any(k in u for k in ACTION_KEYWORDS["confirm"])
        has_question = any(k in u for k in ACTION_KEYWORDS["ask_question"])
        has_off_topic = any(k in u for k in ACTION_KEYWORDS["off_topic"])

        # 「明白了，那我得多接单？」类：表面配合实则追问，应走 ask_question 而非推进 FSM
        if has_comply and has_question:
            stripped = u.replace("？", "").replace("?", "").strip()
            simple_ack = stripped in {"好", "行", "嗯", "成", "可以", "明白", "知道了", "好的", "好吧", "好嘞"}
            substantive_q = (
                not simple_ack
                and (
                    any(k in u for k in REAL_QUESTION_MARKERS)
                    or ("那" in u and ("？" in u or "?" in u))
                )
            )
            if substantive_q:
                return ActionResult("ask_question", 0.87, "keyword", raw_utterance=u)
            return ActionResult("comply", 0.88, "keyword", raw_utterance=u)
        if has_question and (has_off_topic or is_oob_scope_question(u)):
            return ActionResult("off_topic", 0.88, "keyword", raw_utterance=u)
        if has_question:
            return ActionResult("ask_question", 0.86, "keyword", raw_utterance=u)
        if has_off_topic:
            return ActionResult("off_topic", 0.84, "keyword", raw_utterance=u)
        if has_confirm:
            return ActionResult("confirm", 0.85, "keyword", raw_utterance=u)
        if has_comply:
            return ActionResult("comply", 0.82, "keyword", raw_utterance=u)
        if looks_like_acknowledgment(u):
            return ActionResult("comply", 0.78, "acknowledgment", raw_utterance=u)
        return ActionResult("unknown", 0.25, "keyword", needs_review=True, raw_utterance=u)

    async def _llm_classify(self, utterance: str, *, context: Dict[str, Any]) -> ActionResult:
        from eval1.layer2.robust_llm import RobustLLMCall

        fsm_state = str(context.get("fsm_state") or "")
        prompt = f"""分类骑手电话回复的语义动作，只输出JSON：
{{"action":"comply|reject|ask_question|off_topic|hangup|confirm|unknown","confidence":0.0-1.0}}

当前通话阶段：{fsm_state or "未知"}
骑手说：「{utterance}」"""
        caller = RobustLLMCall(component="action_detector")
        text, status = await caller.call_with_fallback(
            primary_fn=lambda: caller.chat(
                system_prompt="你是对话动作分类器，只输出JSON。",
                user_prompt=prompt,
                model=settings.llm_model_fast,
                temperature=0.1,
            ),
            fallback_value='{"action":"unknown","confidence":0.0}',
            validator=lambda s: "action" in s,
            max_retry=1,
            timeout=12.0,
        )
        if status == "degraded":
            return ActionResult("unknown", 0.0, "llm_degraded", needs_review=True, raw_utterance=utterance)
        try:
            payload = json.loads(text.strip())
            action = str(payload.get("action", "unknown"))
            conf = float(payload.get("confidence", 0.0))
            if action not in FSM_ACTIONS:
                action = "unknown"
            return ActionResult(
                action=action,
                confidence=conf,
                source="llm",
                needs_review=conf < self.LLM_MIN_CONFIDENCE,
                raw_utterance=utterance,
            )
        except Exception:
            return ActionResult("unknown", 0.0, "llm_parse_error", needs_review=True, raw_utterance=utterance)

    def verify_for_sampled(self, utterance: str, sampled_action: str, *, strict: bool = False) -> bool:
        """Check utterance reflects intended action semantics (for user sim retry)."""
        u = (utterance or "").strip()
        if not u:
            return False
        detected = self.detect_sync(u, default=sampled_action if strict else "")
        if detected.action == "unknown":
            return sampled_action in {"comply", "confirm"} and len(u) >= 2 and not strict
        if strict:
            if sampled_action == "ask_question":
                return detected.action in {"ask_question", "off_topic"}
            return detected.action == sampled_action
        if sampled_action == "ask_question":
            return detected.action in {"ask_question", "comply"}
        if sampled_action == "reject":
            return detected.action in {"reject", "comply"}
        if sampled_action == "off_topic":
            return detected.action in {"off_topic", "comply"}
        if sampled_action in {"comply", "confirm"}:
            return detected.action in {"comply", "confirm", "reject"}
        return detected.action == sampled_action or detected.action != "unknown"
