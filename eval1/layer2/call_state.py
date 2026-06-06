from __future__ import annotations

from typing import Optional

from eval1.layer2.user_sim_instruction_context import get_flow_step_hint

STATE_TOPICS = {
    "START": "确认来电身份，回应对方问候",
    "F1": "回应当前步骤的第一个业务要点",
    "F2": "回应当前步骤的业务要求",
    "F3": "回应当前步骤的提醒或挽留",
    "F4": "回应当前步骤的规则说明",
    "OBJECTION": "表达对规则的不满或拒绝配合",
    "F3_RETAIN": "在对方挽留下表达犹豫、提条件或仍想拒绝",
    "FAQ_NORMAL": "针对刚听到的内容追问一个还不清楚的细节",
    "FAQ_OOB": "短暂岔到业务场景边缘的无关问题",
    "CLOSING": "对整通电话做最后确认，准备挂断",
    "OBJ_FINAL": "坚持无法继续配合",
    "END": "结束通话",
}


def get_state_topic(current_state: str, *, instruction: Optional[object] = None) -> str:
    step_hint = get_flow_step_hint(instruction, current_state)
    if step_hint:
        return f"回应：{step_hint}"
    return STATE_TOPICS.get(current_state, "自然回应当前通话内容")
