from __future__ import annotations

from typing import List, Optional, Tuple

from eval1.layer1.faq_step_context import faq_interrupt_flow_step
from eval1.layer1.path_probe import (
    PROBE_D10_DRIVE,
    PROBE_D9_BUSY,
    is_probe_node,
    probe_user_line,
)
from eval1.layer2.goal_fsm import GoalFSM
from eval1.layer2.mandatory_scripts import infer_branch_user_hint

# Actions required to visit the next node on an enumerated Layer1 path.
PATH_COVERAGE_ACTIONS = frozenset({"ask_question", "reject", "off_topic", "confirm", "hangup"})

_PATH_CONTEXT_SUFFIX = "（只约束动作类型与路径节点，不规定具体台词；须承接对方上一句要点后自主措辞）"


_NODE_ACTION_HINTS = {
    "F1": "动作为 comply：自然确认身份",
    "F2": "动作为 comply：针对对方刚说的内容表示知晓或回应",
    "F3": "动作为 comply：针对当前说明表示理解并接话",
    "F4": "动作为 comply：针对规则/选项说明回应，表示理解或配合",
    "CLOSING": "动作为 confirm：确认结论，准备结束",
    "FAQ_NORMAL": "动作为 ask_question：结合Bot刚说的内容与上下文追问一句",
    "FAQ_OOB": "动作为 off_topic：在业务场景内提一个需边界回应的跑题问题",
    PROBE_D9_BUSY: "动作为 comply：表示现在很忙，请对方简短说明",
    PROBE_D10_DRIVE: "动作为 comply：表示正在开车，不方便长聊",
    "F3_RETAIN": "动作为 reject：表达犹豫/拒绝以触发挽留",
    "OBJECTION": "动作为 reject：质疑规则或表示不想配合",
    "OBJ_FINAL": "动作为 reject：坚持无法继续",
    "END": "动作为 hangup/confirm：结束通话",
}

_ACTION_FOR_NEXT_NODE = {
    "FAQ_NORMAL": "ask_question",
    "FAQ_OOB": "off_topic",
    "F3_RETAIN": "reject",
    "OBJECTION": "reject",
    "OBJ_FINAL": "reject",
}


def next_path_node(fsm: GoalFSM) -> str:
    planned = fsm.planned_next_nodes(limit=1)
    return planned[0] if planned else ""


def infer_path_user_action(fsm: GoalFSM) -> Tuple[str, str, str]:
    """Infer user action from the next node on the enumerated path."""
    nxt = next_path_node(fsm)
    cur = fsm.current_state

    if fsm.is_terminal() or cur == "END":
        return "hangup", "END", _NODE_ACTION_HINTS["END"]

    if is_probe_node(cur):
        hint = _NODE_ACTION_HINTS.get(cur, probe_user_line(cur))
        return "comply", nxt or cur, hint

    if not nxt:
        if cur == "CLOSING":
            return "confirm", "END", _NODE_ACTION_HINTS["CLOSING"]
        return "comply", "", "动作为 comply：配合Bot当前说明"

    if is_probe_node(nxt):
        hint = _NODE_ACTION_HINTS.get(nxt, probe_user_line(nxt))
        return "comply", nxt, hint

    if nxt in _ACTION_FOR_NEXT_NODE:
        action = _ACTION_FOR_NEXT_NODE[nxt]
        hint = _NODE_ACTION_HINTS.get(nxt, "按路径自然回应")
        if nxt == "FAQ_NORMAL":
            step = faq_interrupt_flow_step(fsm.path_nodes)
            if step:
                hint = (
                    f"动作为 ask_question：结合 Bot 在 {step} 刚说的内容与上下文追问；"
                    f"知识库方向仅供参考，勿照抄{_PATH_CONTEXT_SUFFIX}"
                )
        return action, nxt, hint

    if nxt.startswith("branch::"):
        branch_hint = infer_branch_user_hint(fsm.path_nodes, current_state=cur)
        if branch_hint:
            return "comply", nxt, branch_hint
        return "comply", nxt, "动作为 comply：配合Bot当前说明"

    if cur == "F4":
        branch_hint = infer_branch_user_hint(fsm.path_nodes, current_state=cur)
        if branch_hint:
            return "comply", nxt or branch_hint, branch_hint

    if nxt.startswith("F") or nxt == "CLOSING":
        if nxt == "CLOSING":
            hint = _NODE_ACTION_HINTS["CLOSING"]
            if cur == "F4":
                hint = (
                    "动作为 confirm：针对 Bot 刚说的排名/拒单/天气等要点简短确认已理解，"
                    "准备结束通话（勿说「先听一下/您继续说」）"
                )
            return "confirm", nxt, hint
        if cur in {"FAQ_NORMAL", "FAQ_OOB"}:
            return "comply", nxt, "动作为 comply：理解Bot解释后继续配合"
        if cur in {"F3_RETAIN", "OBJECTION"}:
            return "comply", nxt, "动作为 comply：态度软化，愿意继续"
        if cur == "START":
            return "comply", nxt, _NODE_ACTION_HINTS.get(nxt, "动作为 comply：确认身份")
        return "comply", nxt, _NODE_ACTION_HINTS.get(nxt, "动作为 comply：配合推进")

    if nxt == "END":
        return "confirm", nxt, _NODE_ACTION_HINTS["END"]

    return "comply", nxt, "动作为 comply：自然回应"


def path_coverage_action(
    path_user_action: str,
    required_action: str,
    allowed_actions: List[str],
) -> Optional[str]:
    """
    When the enumerated path's next node needs FAQ / retain / OOB, return that
    user action so Layer2 simulations cover the path (not persona-random only).
    """
    if not path_user_action or path_user_action not in allowed_actions:
        return None
    if path_user_action not in PATH_COVERAGE_ACTIONS:
        return None
    if required_action == "advance_flow":
        return path_user_action
    if required_action == "resolve_objection" and path_user_action in {
        "reject",
        "comply",
        "ask_question",
    }:
        return path_user_action
    if required_action == "close_dialogue" and path_user_action in {"confirm", "hangup"}:
        return path_user_action
    if required_action == "terminate" and path_user_action == "hangup":
        return path_user_action
    return None


def path_action_label(action: str) -> str:
    labels = {
        "comply": "配合确认",
        "confirm": "确认收口",
        "ask_question": "追问细节",
        "reject": "拒绝或质疑",
        "off_topic": "跑题闲聊",
        "hangup": "挂断结束",
    }
    return labels.get(action, action)
