from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TurnTrace:
    turn_index: int
    fsm_state_before: str
    fsm_state_after: str
    user_utterance: str = ""
    detected_action: str = ""
    action_confidence: float = 0.0
    action_source: str = ""
    action_needs_review: bool = False
    retain_success: bool = False
    fsm_moved: bool = False
    fsm_transition_reason: str = ""
    bot_utterance: str = ""
    bot_action: str = ""
    violations_this_turn: List[Dict[str, Any]] = field(default_factory=list)
    degraded_calls: List[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "fsm_state_before": self.fsm_state_before,
            "fsm_state_after": self.fsm_state_after,
            "user_utterance": self.user_utterance,
            "detected_action": self.detected_action,
            "action_confidence": round(self.action_confidence, 3),
            "action_source": self.action_source,
            "action_needs_review": self.action_needs_review,
            "retain_success": self.retain_success,
            "fsm_moved": self.fsm_moved,
            "fsm_transition_reason": self.fsm_transition_reason,
            "bot_utterance": self.bot_utterance,
            "bot_action": self.bot_action,
            "violations_this_turn": list(self.violations_this_turn),
            "degraded_calls": list(self.degraded_calls),
            "duration_ms": self.duration_ms,
        }


@dataclass
class DialogueTrace:
    dialogue_id: str = ""
    plan_id: str = ""
    path_id: str = ""
    persona_type: str = ""
    turns: List[TurnTrace] = field(default_factory=list)
    unknown_action_count: int = 0
    degraded_call_count: int = 0

    def append(self, turn: TurnTrace) -> None:
        self.turns.append(turn)
        if turn.detected_action == "unknown":
            self.unknown_action_count += 1
        self.degraded_call_count += len(turn.degraded_calls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dialogue_id": self.dialogue_id,
            "plan_id": self.plan_id,
            "path_id": self.path_id,
            "persona_type": self.persona_type,
            "turn_count": len(self.turns),
            "unknown_action_count": self.unknown_action_count,
            "degraded_call_count": self.degraded_call_count,
            "turns": [t.to_dict() for t in self.turns],
        }
