from __future__ import annotations

from typing import List, Optional

from eval1.layer2.persona import PersonaCard, PersonaType
from eval1.layer2.call_state import get_state_topic
from eval1.layer2.persona_phrasing import get_persona_tone_for_action
from eval1.layer2.user_sim_instruction_context import UserSimScene, get_flow_step_hint, _DEFAULT_SCENE

_ACTION_LABELS = {
    "comply": "配合确认",
    "confirm": "确认收口",
    "ask_question": "追问细节",
    "reject": "拒绝或质疑",
    "off_topic": "跑题闲聊",
    "hangup": "挂断结束",
}

_STATE_BEHAVIOR = {
    "START": {
        "desc": "确认身份，回应来电",
        "forbidden": ["主动介绍业务规则", "代替Bot推进流程"],
    },
    "F1": {
        "desc": "回应当前步骤的第一个要点",
        "forbidden": ["跳过Bot当前问题直接聊后续规则"],
    },
    "F2": {
        "desc": "回应当前步骤的业务要求",
        "forbidden": ["无视Bot刚说的规则另起话题"],
    },
    "F3": {
        "desc": "回应当前步骤的提醒或挽留",
        "forbidden": ["重复已确认过的内容"],
    },
    "F4": {
        "desc": "回应当前步骤的规则说明",
        "forbidden": ["重复追问Bot已解释过的同一规则"],
    },
    "OBJECTION": {
        "desc": "表达顾虑、质疑规则合理性",
        "allowed_extra": ["reject", "ask_question"],
        "forbidden": ["突然完全同意", "主动帮Bot总结流程"],
    },
    "F3_RETAIN": {
        "desc": "在挽留阶段表达犹豫或提出条件",
        "allowed_extra": ["reject", "ask_question"],
        "forbidden": ["无过渡地突然完全配合", "重复上一句原话"],
    },
    "FAQ_NORMAL": {
        "desc": "围绕当前疑问追问，等待Bot解释",
        "allowed_extra": ["ask_question"],
        "forbidden": ["替Bot回答业务问题", "重复已问过的问题"],
    },
    "FAQ_OOB": {
        "desc": "短暂跑题但可被拉回",
        "allowed_extra": ["off_topic", "ask_question"],
        "forbidden": ["完全脱离当前业务场景"],
    },
    "CLOSING": {
        "desc": "确认结论或做最后确认",
        "allowed_extra": ["confirm"],
        "forbidden": ["重新开启新异议"],
    },
    "END": {
        "desc": "结束通话",
        "forbidden": ["继续业务讨论"],
    },
}


def get_user_directive(
    *,
    current_state: str,
    persona: PersonaCard,
    allowed_actions: List[str],
    required_action: str,
    questions_at_step: int = 0,
    planned_path_nodes: List[str] | None = None,
    path_user_action: str = "",
    path_next_node: str = "",
    path_utterance_hint: str = "",
    instruction: Optional[object] = None,
    scene: UserSimScene | None = None,
) -> str:
    """Generate Goal-FSM behavior directive without exposing full task instruction text."""
    scene = scene or _DEFAULT_SCENE
    behavior = dict(_STATE_BEHAVIOR.get(current_state, {"desc": "自然回应当前通话", "forbidden": []}))
    step_hint = get_flow_step_hint(instruction, current_state)
    if step_hint:
        behavior["desc"] = f"回应：{step_hint}"

    allowed_labels = [_ACTION_LABELS.get(a, a) for a in allowed_actions if a in _ACTION_LABELS]
    forbidden = list(behavior.get("forbidden") or [])

    if persona.persona_type == PersonaType.RESISTANT and current_state in {"OBJECTION", "F3_RETAIN"}:
        if questions_at_step < 2:
            forbidden.append("立即完全同意")
        else:
            forbidden = [f for f in forbidden if f != "无过渡地突然完全配合"]

    if persona.persona_type == PersonaType.COOPERATIVE:
        forbidden.append("无故拒绝或反复刁难")

    if persona.persona_type == PersonaType.IMPATIENT:
        forbidden.append("长篇大论")
        forbidden.append("在流程后期突然质疑规则")

    lines = [
        f"当前通话：{get_state_topic(current_state, instruction=instruction)}。",
        f"本轮目标：{behavior.get('desc', '自然回复')}。",
        f"FSM要求动作：{required_action}。",
        f"允许的行为：{'、'.join(allowed_labels) or '自然回复'}。",
        f"禁止：{'、'.join(forbidden) or '无'}。",
    ]
    if planned_path_nodes:
        lines.append("后续通话还会涉及更多规则说明，按当前Persona自然回应即可。")
    if path_user_action:
        action_label = _ACTION_LABELS.get(path_user_action, path_user_action)
        lines.append(f"【路径动作·硬约束】本轮用户动作必须是：{action_label}（只约束动作类型，不规定原话）。")
        if path_utterance_hint:
            lines.append(f"路径说明：{path_utterance_hint}")
        tone = get_persona_tone_for_action(persona, path_user_action)
        lines.append(f"【Persona语气·软约束】{tone}")
        if path_user_action == "reject" and persona.persona_type == PersonaType.COOPERATIVE:
            lines.append("配合型也需用礼貌方式表达困难/暂缓，语义上仍是拒绝。")
    lines.append("禁止引用或执行完整Call Flow，你只知道通话中Bot已告知的信息。")
    return "\n".join(lines)


def build_persona_card_block(
    persona: PersonaCard,
    *,
    user_name: str = "",
    user_role: str = "接听电话的用户",
) -> str:
    """Persona card section for user simulator system prompt."""
    if user_name:
        who = f"你是{user_role}{user_name}，"
    else:
        who = f"你是{user_role}，"
    patterns = "、".join(persona.utterance_patterns or [])
    return (
        f"{who}当前Persona={persona.persona_type.value}。\n"
        f"情绪状态：{persona.emotion_description}\n"
        f"角色行为：{persona.system_prompt_fragment}\n"
        f"配合度：{persona.cooperation_level:.2f}（0=完全不配合，1=完全配合）\n"
        f"表达特征（风格参考，勿逐字照搬）：{patterns or '自然口语'}"
    )


def format_dialogue_history(messages: List[dict], limit: int = 10) -> str:
    """Format recent dialogue turns for user simulator context."""
    recent = list(messages or [])[-limit:]
    if not recent:
        return "（暂无历史）"
    lines: List[str] = []
    for m in recent:
        role = str(m.get("role", "")).upper()
        if role not in {"USER", "BOT"}:
            continue
        content = str(m.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "（暂无历史）"
