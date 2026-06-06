from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from eval1.layer2.action_detector import detect_actual_action
from eval1.layer2.persona import PersonaCard

_PREFIX_FACT = "fact:"
_PREFIX_STANCE = "stance:"
_PREFIX_CONCERN = "concern:"
_PREFIX_QUESTION = "question:"


@dataclass
class UserContextMemory:
    """Structured rider-side memory for adaptive user simulation."""

    bot_facts: List[str] = field(default_factory=list)
    user_stances: List[str] = field(default_factory=list)
    open_concerns: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    @classmethod
    def from_legacy(cls, items: List[str] | None) -> UserContextMemory:
        mem = cls()
        for raw in items or []:
            mem._absorb_one(str(raw).strip())
        return mem

    @classmethod
    def from_dialogue(
        cls,
        *,
        user_memory: List[str] | None,
        messages: List[dict] | None,
        user_history: List[str] | None,
    ) -> UserContextMemory:
        mem = cls.from_legacy(user_memory)
        for utter in user_history or []:
            u = str(utter).strip()
            if u and not any(u in s or s.endswith(u[:12]) for s in mem.user_stances):
                action = detect_actual_action(u)
                mem.update_from_user(u, action, merge_only=True)
        return mem

    def _absorb_one(self, item: str) -> None:
        if not item:
            return
        if item.startswith(_PREFIX_FACT):
            self._add_unique(self.bot_facts, item[len(_PREFIX_FACT) :].strip())
        elif item.startswith(_PREFIX_STANCE):
            self._add_unique(self.user_stances, item[len(_PREFIX_STANCE) :].strip())
        elif item.startswith(_PREFIX_CONCERN):
            self._add_unique(self.open_concerns, item[len(_PREFIX_CONCERN) :].strip())
        elif item.startswith(_PREFIX_QUESTION):
            self._add_unique(self.open_questions, item[len(_PREFIX_QUESTION) :].strip())
        else:
            self._add_unique(self.bot_facts, item)

    @staticmethod
    def _add_unique(bucket: List[str], text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        if t in bucket:
            return
        if any(t[:10] == x[:10] for x in bucket if len(t) >= 10 and len(x) >= 10):
            return
        bucket.append(t[:80])

    def absorb_bot_snippets(self, snippets: List[str]) -> None:
        for s in snippets:
            self._add_unique(self.bot_facts, s)

    def update_from_user(self, utterance: str, action: str, *, merge_only: bool = False) -> None:
        u = (utterance or "").strip()
        if not u:
            return
        summary = _summarize_utterance(u)
        if action == "reject":
            self._add_unique(self.open_concerns, summary)
        elif action == "ask_question":
            self._add_unique(self.open_questions, summary)
            if not merge_only:
                self.open_questions = self.open_questions[-5:]
        elif action in {"comply", "confirm"}:
            self._add_unique(self.user_stances, summary)
            if not merge_only:
                self._resolve_answered_questions(u)
        elif action == "off_topic":
            self._add_unique(self.open_concerns, f"曾岔题：{summary}")

    def _resolve_answered_questions(self, utterance: str) -> None:
        if not self.open_questions:
            return
        u = utterance.lower()
        remaining = []
        for q in self.open_questions:
            key = re.sub(r"[？?吗呢吧]", "", q)[:6]
            if key and key in u:
                continue
            remaining.append(q)
        self.open_questions = remaining

    def to_legacy_list(self) -> List[str]:
        out: List[str] = []
        for f in self.bot_facts[-12:]:
            out.append(f"{_PREFIX_FACT}{f}")
        for s in self.user_stances[-8:]:
            out.append(f"{_PREFIX_STANCE}{s}")
        for c in self.open_concerns[-6:]:
            out.append(f"{_PREFIX_CONCERN}{c}")
        for q in self.open_questions[-4:]:
            out.append(f"{_PREFIX_QUESTION}{q}")
        return out

    def format_for_prompt(self, persona: PersonaCard, *, caller_label: str = "来电方") -> str:
        lines = [
            f"配合倾向：{persona.cooperation_level:.0%}（越高越愿意口头同意，越低越爱质疑/拒绝）",
            f"打断/跑题倾向：中断{persona.interruption_prob:.0%}，跑题{persona.off_topic_prob:.0%}",
        ]
        if self.bot_facts:
            lines.append(f"{caller_label}已告知：" + "；".join(self.bot_facts[-8:]))
        else:
            lines.append(f"{caller_label}已告知：（通话刚开始，信息尚少）")
        if self.user_stances:
            lines.append("你之前已表态：" + "；".join(self.user_stances[-5:]))
        if self.open_concerns:
            lines.append("你仍有顾虑：" + "；".join(self.open_concerns[-4:]))
        if self.open_questions:
            lines.append("你还没搞清楚的：" + "；".join(self.open_questions[-3:]))
        return "\n".join(lines)

    def dialogue_position(self, *, last_bot: str, current_topic: str, caller_label: str = "来电方") -> str:
        parts = [f"当前话题：{current_topic}"]
        if last_bot:
            parts.append(f"{caller_label}刚说完：「{last_bot[:60]}」")
        if self.user_stances:
            parts.append(f"你此前态度：{self.user_stances[-1]}")
        if self.open_concerns and not self.user_stances:
            parts.append("你对规则仍有防备")
        return "；".join(parts)


def _summarize_utterance(text: str) -> str:
    t = re.sub(r"\s+", "", (text or "").strip())
    return t[:40] if t else ""


def merge_bot_knowledge(memory: UserContextMemory, new_snippets: List[str]) -> List[str]:
    memory.absorb_bot_snippets(new_snippets)
    return memory.to_legacy_list()


def merge_user_turn(memory: UserContextMemory, utterance: str, action: str) -> List[str]:
    memory.update_from_user(utterance, action)
    return memory.to_legacy_list()
