from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from eval1.layer2.instruction_injection import substitute_variables
from eval1.layer2.instruction_profile import InstructionProfile, build_instruction_profile
from eval1.layer2.user_role_guard import user_facing_task_summary


@dataclass(frozen=True)
class UserSimScene:
    """User-side call context derived from the active task instruction."""

    caller_label: str
    user_role: str
    user_name: str
    task_summary: str
    max_chars: int
    scene_block: str
    off_topic_scope: str
    forbidden_phrases: tuple[str, ...] = ()


_DEFAULT_SCENE = UserSimScene(
    caller_label="来电方",
    user_role="接听电话的用户",
    user_name="",
    task_summary="自然回应当前通话内容",
    max_chars=25,
    scene_block=(
        "【通话场景】\n"
        "你是接听电话的用户，正在与对方通话。\n"
        "回复须像真实电话口语：短句、直接，带Persona情绪。"
    ),
    off_topic_scope="当前业务场景边缘",
)


def _first_nonempty(*parts: str) -> str:
    for p in parts:
        t = (p or "").strip()
        if t:
            return t
    return ""


def _extract_inline_section(header: str) -> tuple[str, str]:
    h = (header or "").strip()
    low = h.lower()
    for key, aliases in (
        ("role", ("role",)),
        ("task", ("task",)),
        ("opening_line", ("opening line", "opening")),
    ):
        for alias in aliases:
            if low.startswith(alias):
                sep = re.search(r"[:：]", h)
                if sep:
                    return key, h[sep.end() :].strip()
                return key, ""
    return "", ""


def _infer_max_chars(instruction: Any) -> int:
    for c in list(getattr(instruction, "constraints", []) or []):
        text = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", ""))
        m = re.search(r"(\d+)\s*[-~到至]\s*(\d+)\s*个?字", text)
        if m:
            return int(m.group(2))
        m = re.search(r"(\d+)\s*个?字", text)
        if m:
            return int(m.group(1))
        if "30" in text and "字" in text:
            return 30
    return 25


def _scene_from_profile(profile: InstructionProfile, instruction: Any, slots: Dict[str, str]) -> UserSimScene:
    user_name = _first_nonempty(
        str(slots.get("rider_name", "")),
        str(slots.get("contact_name", "")),
        str(slots.get("user_name", "")),
    )
    max_chars = _infer_max_chars(instruction)
    name_part = f"（{user_name}）" if user_name else ""
    listener_summary = user_facing_task_summary(profile.active_domains, profile.user_role)
    scene_block = (
        "【通话场景】\n"
        f"你是{profile.user_role}{name_part}，正在接听{profile.caller_label}的电话。\n"
        f"通话背景：{listener_summary}\n"
        f"回复须像真实电话口语：短句、直接，带Persona情绪；每轮不超过{max_chars}字。\n"
        f"你是接听方，不是{profile.caller_label}；禁止以「我们做了升级」等口吻替对方宣告业务内容。"
    )
    if profile.forbidden_phrases:
        scene_block += f"\n禁止出现与当前任务无关的表述：{'、'.join(profile.forbidden_phrases[:12])}。"
    return UserSimScene(
        caller_label=profile.caller_label,
        user_role=profile.user_role,
        user_name=user_name,
        task_summary=listener_summary,
        max_chars=max_chars,
        scene_block=scene_block,
        off_topic_scope=profile.off_topic_scope,
        forbidden_phrases=profile.forbidden_phrases,
    )


def build_user_sim_scene(instruction: Any | None, slots: Dict[str, str] | None = None) -> UserSimScene:
    """Build user-simulator scene from ParsedInstruction (same source as bot prompt)."""
    if instruction is None:
        return _DEFAULT_SCENE
    slots = dict(slots or {})
    profile = build_instruction_profile(instruction, slots)
    return _scene_from_profile(profile, instruction, slots)


def get_flow_step_hint(instruction: Any | None, current_state: str) -> str:
    if not instruction or not current_state.startswith("F"):
        return ""
    try:
        idx = int(current_state[1:]) - 1
    except ValueError:
        return ""
    steps: List[str] = list(getattr(instruction, "flow_steps", []) or [])
    if 0 <= idx < len(steps):
        step = re.sub(r"\*\*[^*]+\*\*", "", str(steps[idx])).strip()
        step = re.sub(r"^[-•]\s*", "", step)
        if len(step) > 72:
            step = step[:71] + "…"
        return step
    return ""


def parse_inline_section_key(header: str) -> tuple[str, str]:
    return _extract_inline_section(header)


def infer_user_sim_domain(instruction: Any | None, slots: Dict[str, str] | None = None) -> str:
    """Primary active domain label inferred from instruction text (not dataset id)."""
    profile = build_instruction_profile(instruction, slots)
    if profile.active_domains:
        return profile.active_domains[0]
    return "generic"
