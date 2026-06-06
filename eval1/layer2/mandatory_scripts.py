from __future__ import annotations

from typing import Any, Mapping, Sequence

from eval1.layer1.instruction_capabilities import instruction_has_flow_branches
from eval1.layer2.instruction_injection import substitute_variables
from eval1.layer2.step_speakable import extract_step_scripts, resolve_branch_speakable

# F4.1 询问完整播报（超 30 字，评测豁免）
_F4_PUBLISH_ASK_MARKERS = ("Web控制台", "校务系统", "SaaS", "发课")


def _raw(instruction: Any) -> str:
    return str(getattr(instruction, "raw_text", "") or "")


def _first_ask_script(instruction: Any, step_no: int, slots: Mapping[str, str]) -> str:
    for line in extract_step_scripts(_raw(instruction), step_no):
        if "？" in line or "?" in line or line.endswith("吗"):
            return substitute_variables(line.strip(), dict(slots)).strip()
    return ""


def _first_ref_script(instruction: Any, step_no: int, slots: Mapping[str, str]) -> str:
    for line in extract_step_scripts(_raw(instruction), step_no):
        if "？" not in line and "?" not in line and not line.endswith("吗"):
            return substitute_variables(line.strip(), dict(slots)).strip()
    return ""


def _delivered(bot_state: Mapping[str, object] | None, key: str) -> bool:
    if not bot_state:
        return False
    bag = bot_state.get("mandatory_delivered")
    if isinstance(bag, (set, frozenset)):
        return key in bag
    if isinstance(bag, list):
        return key in bag
    return bool(bot_state.get(key))


def _mark_delivered(bot_state: dict[str, object], key: str) -> None:
    bag = bot_state.get("mandatory_delivered")
    if isinstance(bag, set):
        bag.add(key)
    elif isinstance(bag, list):
        if key not in bag:
            bag.append(key)
    else:
        bot_state["mandatory_delivered"] = [key]
    bot_state[key] = True


def is_mandatory_script_exempt(utterance: str) -> bool:
    t = (utterance or "").strip()
    if not t:
        return False
    if any(m in t for m in _F4_PUBLISH_ASK_MARKERS):
        return True
    if "标准直播" in t and "低延迟" in t and "知道吗" in t:
        return True
    if "低延迟直播" in t and "选项" in t and "升级" in t:
        return True
    return False


def infer_branch_user_hint(
    planned_nodes: Sequence[str],
    *,
    current_state: str = "",
) -> str:
    """Guide user sim to answer in a way that matches the enumerated branch on the path."""
    nodes = list(planned_nodes or [])
    upcoming = ""
    if current_state in nodes:
        idx = nodes.index(current_state)
        for n in nodes[idx + 1 : idx + 4]:
            if str(n).startswith("branch::"):
                upcoming = str(n)
                break
    if not upcoming:
        for n in nodes:
            if str(n).startswith("branch::4::"):
                upcoming = str(n)
                break
    if not upcoming.startswith("branch::"):
        return ""

    if upcoming.startswith("branch::4::"):
        if "Web" in upcoming or "控制台" in upcoming:
            base = "动作为 comply：说明您通过 Web 控制台发课"
        elif "第三方" in upcoming:
            base = "动作为 comply：说明您用第三方/校务或 SaaS 系统发课"
        else:
            base = "动作为 comply：回答您的发课方式"
        if upcoming.endswith("::1") or upcoming.endswith("::3") or "已显示" in upcoming:
            return f"{base}，且前端已能看到低延迟选项（承接 Bot 刚问的发布方式）"
        if upcoming.endswith("::2") or upcoming.endswith("::4") or "未显示" in upcoming:
            return f"{base}，但还没看到低延迟选项（承接 Bot 刚问的发布方式）"
        return f"{base}（须承接 Bot 4.1 询问后作答，措辞自主）"

    if upcoming.startswith("branch::2::"):
        if "main::2" in upcoming or "知情" in upcoming:
            return "动作为 comply：表示之前就知道/知情（承接 Bot 是否知情的询问）"
        return "动作为 comply：表示不太清楚/之前不知道（承接 Bot 是否知情的询问）"

    if upcoming.startswith("branch::5::"):
        if "main::2" in upcoming or "已设置" in upcoming:
            return "动作为 comply：表示学员端费用已经设好了（承接 Bot 费用相关说明）"
        return "动作为 comply：表示费用还没设或不清楚（承接 Bot 费用相关说明）"

    if upcoming.startswith("branch::6::"):
        if "main::2" in upcoming or "不可添加" in upcoming:
            return "动作为 comply：表示这个号码加不了微信，可换手机号（承接 Bot 企业微信添加）"
        return "动作为 comply：表示可以用当前号码添加企业微信（承接 Bot 企业微信添加）"

    return ""


def get_mandatory_bot_utterance(
    instruction: Any,
    current_state: str,
    bot_state: dict[str, object] | None,
    *,
    planned_nodes: Sequence[str] | None = None,
    slots: Mapping[str, str] | None = None,
) -> str:
    """
    Instruction_2: deliver specified 询问/参考话术 verbatim when entering key steps.
    Returns "" if LLM/free generation should handle this turn.
    """
    if not instruction or not instruction_has_flow_branches(instruction):
        return ""
    state = str(current_state or "")
    bs = dict(bot_state or {})
    slot_map = dict(slots or {})

    if state.startswith("branch::"):
        line = resolve_branch_speakable(instruction, state, slot_map, max_len=48)
        if line:
            key = f"mandatory_branch:{state}"
            if not _delivered(bs, key):
                if bot_state is not None:
                    _mark_delivered(bot_state, key)
                return line
        return ""

    if state == "F2":
        key_ref = "mandatory:f1_ref"
        if not _delivered(bs, key_ref):
            line = _first_ref_script(instruction, 1, slot_map)
            if line and bot_state is not None:
                _mark_delivered(bot_state, key_ref)
            if line:
                return line
        key = "mandatory:f2_ask"
        if not _delivered(bs, key):
            line = _first_ask_script(instruction, 2, slot_map)
            if line and bot_state is not None:
                _mark_delivered(bot_state, key)
            return line

    if state == "F3":
        key = "mandatory:f3_ref"
        if not _delivered(bs, key):
            line = _first_ref_script(instruction, 3, slot_map)
            if line and bot_state is not None:
                _mark_delivered(bot_state, key)
            return line

    if state == "F4":
        key = "mandatory:f4_publish_ask"
        if not _delivered(bs, key):
            line = _first_ask_script(instruction, 4, slot_map)
            if not line:
                line = "您是通过Web控制台、校务系统A，还是SaaS系统B发课？"
            if bot_state is not None:
                _mark_delivered(bot_state, key)
            return line

    return ""


def mandatory_script_hint(instruction: Any, current_state: str, bot_state: dict[str, object] | None) -> str:
    """Prompt hint when mandatory script applies but was already delivered."""
    if not instruction_has_flow_branches(instruction):
        return ""
    state = str(current_state or "")
    if state == "F4" and _delivered(bot_state, "mandatory:f4_publish_ask"):
        return "【必达已完成】F4.1 发布方式询问已完整播报；根据用户回答进入 Web/第三方 分支，勿重复整句询问。"
    if state == "F2" and _delivered(bot_state, "mandatory:f2_ask"):
        return "【必达已完成】F2 知情询问已播报；按用户回答走知情/不知情分支。"
    return ""
