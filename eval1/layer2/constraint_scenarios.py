from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Sequence

from eval1.layer1.path_probe import PROBE_D10_DRIVE, PROBE_D9_BUSY, is_probe_node, probe_user_line
from eval1.layer2.bot_repeat_guard import is_busy_or_refuse_user
from eval1.layer2.instruction_grounding import find_constraint_lines

_DRIVE_MARKERS = ("开车", "驾驶", "在高速", "驾车")


def is_driving_user(text: str) -> bool:
    u = (text or "").strip()
    return bool(u) and any(m in u for m in _DRIVE_MARKERS)


def build_driving_hangup_alts(instruction: Any) -> List[str]:
    alts: List[str] = []
    for line in find_constraint_lines(instruction, "开车", "驾驶", "稍后再打"):
        m = re.search(r"[「\"']([^」\"']+)[」\"']", line)
        if m and "打" in m.group(1):
            alts.append(m.group(1).strip())
        elif "稍后再打" in line:
            alts.append("那我稍后再打，再见。")
    for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
        text = str(getattr(kn, "text", kn) if not isinstance(kn, dict) else kn.get("text", ""))
        if "开车" not in text:
            continue
        m = re.search(r"】\s*([^【]+)", text)
        if m:
            reply = m.group(1).strip()
            if reply and reply not in alts:
                alts.append(reply)
    if not alts:
        alts = [
            "那我稍后再打，再见。",
            "您先注意安全，我稍后再联系。",
        ]
    return alts


def build_busy_brief_alts(instruction: Any) -> List[str]:
    for line in find_constraint_lines(instruction, "忙", "1分钟", "1 分钟", "简短"):
        m = re.search(r"[「\"']([^」\"']+)[」\"']", line)
        if m and ("分钟" in m.group(1) or "简短" in m.group(1)):
            return [m.group(1).strip()]
        if "1分钟" in line or "1 分钟" in line:
            return ["就1分钟，保证简短。"]
    return ["就1分钟，保证简短。"]


def _matches_probe_script(text: str, probe_node: str) -> bool:
    script = probe_user_line(probe_node)
    u = (text or "").strip()
    if script and script in u:
        return True
    if probe_node == PROBE_D10_DRIVE:
        return is_driving_user(u)
    if probe_node == PROBE_D9_BUSY:
        return is_busy_or_refuse_user(u) and not is_driving_user(u)
    return False


@dataclass(frozen=True)
class ScenarioReply:
    text: str
    force_end: bool = False
    mark_busy_briefed: bool = False
    probe_prompt: bool = False


def resolve_scenario_reply(
    instruction: Any,
    *,
    last_user_utterance: str,
    bot_state: dict,
    current_state: str,
    path_nodes: Sequence[str] | None = None,
) -> ScenarioReply | None:
    """Mandatory bot lines for D9 busy / D10 driving and probe pacing."""
    last = (last_user_utterance or "").strip()
    if not last:
        return None

    nodes = list(path_nodes or [])
    state = str(current_state or "")

    if is_driving_user(last):
        alts = build_driving_hangup_alts(instruction)
        return ScenarioReply(text=alts[0], force_end=True)

    if is_busy_or_refuse_user(last) and not bot_state.get("busy_briefed"):
        brief = build_busy_brief_alts(instruction)
        if brief:
            return ScenarioReply(text=brief[0], mark_busy_briefed=True)

    if is_probe_node(state) and not _matches_probe_script(last, state):
        return ScenarioReply(text="嗯，您说。", probe_prompt=True)

    if state == "CLOSING" and PROBE_D10_DRIVE in nodes and is_driving_user(last):
        alts = build_driving_hangup_alts(instruction)
        return ScenarioReply(text=alts[0], force_end=True)

    return None
