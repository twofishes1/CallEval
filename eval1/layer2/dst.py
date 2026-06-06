from __future__ import annotations

import re
from typing import Any, Dict, List

from eval1.layer1.models import ParsedInstruction
from eval1.layer2.goal_fsm import GoalFSM


class DST:
    """Dialogue state tracking + realtime lightweight constraint checks."""

    def check_constraints(
        self,
        utterance: str,
        turn_index: int,
        instruction: ParsedInstruction | None,
        fsm: GoalFSM,
        *,
        is_opening_line: bool = False,
        is_f4_delivery: bool = False,
        is_mandatory_script: bool = False,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        txt = utterance or ""
        # DIALOGUE length: Opening Line / F4 完整说明 / 必达询问 不受 30 字限制
        if (
            not is_opening_line
            and not is_f4_delivery
            and not is_mandatory_script
            and len(txt.replace(" ", "")) > 30
        ):
            out.append(
                {
                    "turn_index": turn_index,
                    "violation_type": "dialogue_length",
                    "constraint_id": "D_LEN",
                    "constraint_text": "每轮不超过30字（Opening Line、F4 完整说明、必达询问除外）",
                    "bot_utterance": txt,
                    "explanation": "Bot utterance length exceeds 30 chars.",
                    "deduction": 5.0,
                }
            )
        # BOUNDARY proxy check
        if "不支持" in txt and "可以" in txt:
            out.append(
                {
                    "turn_index": turn_index,
                    "violation_type": "hard_boundary",
                    "constraint_id": "B*",
                    "constraint_text": "边界类约束",
                    "bot_utterance": txt,
                    "explanation": "Bot claims unsupported capability.",
                    "deduction": 100.0,
                }
            )
        return out

    async def detect_step_completion(
        self,
        utterance: str,
        current_state: str,
        instruction: ParsedInstruction | None,
        expected_step_text: str = "",
        *,
        user_action: str = "comply",
    ) -> bool:
        txt = (utterance or "").strip()
        if not txt:
            return False
        if not expected_step_text:
            return user_action in {"comply", "confirm"}
        hits = 0
        for kw in self._extract_keywords(expected_step_text):
            if kw and kw in txt:
                hits += 1
        return hits >= 1

    def user_acknowledged(self, utterance: str) -> bool:
        u = (utterance or "").strip()
        if not u:
            return False
        markers = [
            "知道", "明白", "好的", "可以", "行", "没问题", "确认", "试试",
            "连续", "上线", "准时", "一定", "马上", "这就", "收到",
        ]
        return any(m in u for m in markers)

    async def should_advance_after_user_comply(
        self,
        *,
        last_user_utterance: str,
        last_bot_utterance: str,
        expected_step_text: str,
    ) -> bool:
        """User confirmed after bot spoke on current step → ready to advance."""
        if not self.user_acknowledged(last_user_utterance):
            return False
        if not (last_bot_utterance or "").strip():
            return False
        if any(k in last_user_utterance for k in ["？", "?", "吗", "什么", "为什么", "依据", "怎么"]):
            return False
        return True

    def _extract_keywords(self, text: str) -> List[str]:
        toks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text or "")
        stop = {
            "请问",
            "需要",
            "进行",
            "可以",
            "当前",
            "步骤",
            "用户",
            "任务",
            "流程",
            "对话",
            "确认",
        }
        out: List[str] = []
        for t in toks:
            if t in stop:
                continue
            out.append(t)
        return out[:8]
