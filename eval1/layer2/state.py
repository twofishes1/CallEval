from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from eval1.layer1.models import ExecutionPlan, ParsedInstruction
from eval1.layer2.dialogue_trace import DialogueTrace
from eval1.layer2.goal_fsm import GoalFSM


class BotState(TypedDict, total=False):
    current_step_id: str
    current_step_text: str
    last_bot_utterance: str
    used_knowledge_ids: List[str]
    slot_values: Dict[str, str]
    repeat_guard_window: List[str]
    user_busy_streak: int
    bot_action_log: List[str]
    name_used: bool
    f4_speech_index: int
    f4_delivered: List[str]
    f4_single_utterance: str
    f4_last_utterance: str
    f4_part_index: int


class DialogueState(TypedDict, total=False):
    instruction: ParsedInstruction
    plan: ExecutionPlan
    goal_fsm: GoalFSM
    persona_type: str
    tone_modifier: str
    turn_count: int
    max_turns: int
    messages: List[Dict[str, Any]]
    fsm_log: List[str]
    user_memory: List[str]
    violations: List[Dict[str, Any]]
    should_terminate: bool
    termination_reason: Optional[str]
    hard_violation: bool
    forced_action_retry_count: int
    user_llm_connected: bool
    bot_llm_connected: bool
    path_covered: bool
    flow_adherence_rate: float
    covered_nodes: List[str]
    last_user_action: str
    consecutive_reject: int
    stalled_rounds: int
    step_questions: int
    step_question_state: str
    dialogue_trace: DialogueTrace
    last_action_confidence: float
    last_action_source: str
    last_action_needs_review: bool
    pending_review: bool
    degraded_calls: List[str]
    bot_state: BotState
    bot_state_log: List[BotState]


def make_initial_state(
    *,
    instruction: ParsedInstruction | None,
    plan: ExecutionPlan,
    fsm: GoalFSM,
    persona_type: str,
    tone_modifier: str = "default",
) -> DialogueState:
    from eval1.config import settings

    planned = int(plan.max_turns)
    cap = int(settings.max_turns_absolute)
    # Respect Layer1 plan budget; do not inflate by flow_steps*4 (task2 would hit 48).
    runtime_max = min(cap, planned)
    return {
        "instruction": instruction,
        "plan": plan,
        "goal_fsm": fsm,
        "persona_type": persona_type,
        "tone_modifier": tone_modifier,
        "turn_count": 0,
        "max_turns": runtime_max,
        "messages": [],
        "fsm_log": [fsm.current_state],
        "user_memory": [],
        "violations": [],
        "should_terminate": False,
        "termination_reason": None,
        "hard_violation": False,
        "forced_action_retry_count": 0,
        "user_llm_connected": True,
        "bot_llm_connected": True,
        "path_covered": False,
        "flow_adherence_rate": 0.0,
        "covered_nodes": [fsm.current_state],
        "last_user_action": "comply",
        "consecutive_reject": 0,
        "stalled_rounds": 0,
        "step_questions": 0,
        "step_question_state": "",
        "dialogue_trace": DialogueTrace(
            dialogue_id=str(plan.plan_id),
            plan_id=str(plan.plan_id),
            path_id=str(plan.path.path_id),
            persona_type=str(persona_type),
        ),
        "last_action_confidence": 1.0,
        "last_action_source": "init",
        "last_action_needs_review": False,
        "pending_review": False,
        "degraded_calls": [],
        "bot_state": {
            "current_step_id": fsm.current_state,
            "current_step_text": "",
            "last_bot_utterance": "",
            "used_knowledge_ids": [],
            "slot_values": {str(k): str(v) for k, v in (plan.variable_values or {}).items()},
            "repeat_guard_window": [],
            "user_busy_streak": 0,
            "bot_action_log": [],
            "name_used": False,
        },
        "bot_state_log": [],
    }
