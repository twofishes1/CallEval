from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from eval1.config import settings
from eval1.layer1.models import EnumeratedPath, ExecutionPlan
from eval1.layer1.path_probe import PROBE_D10_DRIVE, PROBE_D9_BUSY
from eval1.layer2.persona import PersonaType

INTERRUPT_NODES = frozenset({"OBJECTION", "F3_RETAIN", "OBJ_FINAL", "FAQ_NORMAL", "FAQ_OOB"})
FAQ_NODES = frozenset({"FAQ_NORMAL", "FAQ_OOB"})
OBJECTION_NODES = frozenset({"OBJECTION", "F3_RETAIN", "OBJ_FINAL"})

_FLOW_NODES = frozenset({"F1", "F2", "F3", "F4", "CLOSING"})


@dataclass(frozen=True)
class PathProfile:
    tags: frozenset[str]

    @property
    def is_mainline(self) -> bool:
        return "mainline" in self.tags

    @property
    def has_faq(self) -> bool:
        return "faq" in self.tags

    @property
    def has_oob(self) -> bool:
        return "oob" in self.tags

    @property
    def has_objection(self) -> bool:
        return "objection" in self.tags


# Persona × path-tag semantic assignment (selective, not cartesian)
_SEMANTIC_MATCH_RULES: Tuple[Tuple[PersonaType, frozenset[str], str], ...] = (
    (PersonaType.COOPERATIVE, frozenset({"mainline"}), "主干顺流程"),
    (PersonaType.IMPATIENT, frozenset({"mainline"}), "主干快路径"),
    (PersonaType.IMPATIENT, frozenset({"probe_busy"}), "D9忙场景探针"),
    (PersonaType.IMPATIENT, frozenset({"probe_drive"}), "D10开车场景探针"),
    (PersonaType.COOPERATIVE, frozenset({"faq"}), "FAQ配合追问"),
    (PersonaType.IMPATIENT, frozenset({"faq"}), "FAQ快问"),
    (PersonaType.QUESTIONING, frozenset({"faq"}), "FAQ业务追问"),
    (PersonaType.IGNORANT, frozenset({"faq"}), "FAQ含义追问"),
    (PersonaType.RESISTANT, frozenset({"faq"}), "FAQ带疑追问"),
    (PersonaType.OFF_TOPIC, frozenset({"faq"}), "FAQ跑题式追问"),
    (PersonaType.RESISTANT, frozenset({"objection"}), "异议挽留路径"),
    (PersonaType.OFF_TOPIC, frozenset({"oob"}), "跑题边界路径"),
)


def profile_path(path: EnumeratedPath) -> PathProfile:
    nodes = set(path.nodes or [])
    tags: set[str] = set()
    if "FAQ_NORMAL" in nodes:
        tags.add("faq")
    if "FAQ_OOB" in nodes:
        tags.add("oob")
    if PROBE_D9_BUSY in nodes:
        tags.add("probe_busy")
    if PROBE_D10_DRIVE in nodes:
        tags.add("probe_drive")
    if nodes & OBJECTION_NODES:
        tags.add("objection")
    if not tags:
        tags.add("mainline")
    return PathProfile(frozenset(tags))


def path_has_interrupt(path: EnumeratedPath, nodes: frozenset[str] | None = None) -> bool:
    pool = nodes or INTERRUPT_NODES
    return any(n in pool for n in (path.nodes or []))


def match_personas_for_path(path: EnumeratedPath) -> List[Tuple[PersonaType, str]]:
    """Return persona types that semantically fit this path (may be 0..N, not always 6)."""
    tags = profile_path(path).tags
    matched: List[Tuple[PersonaType, str]] = []
    seen: set[str] = set()
    for persona, required_tags, reason in _SEMANTIC_MATCH_RULES:
        if tags & required_tags and persona.value not in seen:
            matched.append((persona, reason))
            seen.add(persona.value)
    return matched


def should_skip(path: EnumeratedPath, persona: str | PersonaType) -> Tuple[bool, str]:
    """True when persona is not in the semantic match set for this path."""
    p = persona.value if isinstance(persona, PersonaType) else str(persona or "")
    allowed = {pt.value for pt, _ in match_personas_for_path(path)}
    if p in allowed:
        return False, ""
    prof = profile_path(path)
    if p == PersonaType.QUESTIONING.value and not prof.has_faq:
        return True, "质疑型需含 FAQ 节点以自然追问"
    if p == PersonaType.RESISTANT.value and not prof.has_objection:
        return True, "抵触型需含 OBJECTION/F3_RETAIN 节点"
    if p == PersonaType.IGNORANT.value and not prof.has_faq:
        return True, "懵懂型需含 FAQ 节点以追问含义"
    if p == PersonaType.OFF_TOPIC.value and not prof.has_oob:
        return True, "跑题型需含 FAQ_OOB 节点"
    if p in {PersonaType.COOPERATIVE.value, PersonaType.IMPATIENT.value} and not prof.is_mainline:
        if prof.tags & {"probe_busy", "probe_drive"} and p == PersonaType.IMPATIENT.value:
            return False, ""
        return True, "配合/急躁型仅匹配无中断的主干路径"
    return True, f"{p} 与路径语义标签 {sorted(prof.tags)} 不匹配"


def estimate_plan_max_turns(path: EnumeratedPath, persona: PersonaType) -> int:
    """
    Bot-turn budget from path node costs + persona slack.
    """
    costs = dict(settings.node_turn_cost or {})
    total = int(settings.min_turns_buffer)
    nodes = list(path.nodes or [])

    for n in nodes:
        if n in {"START", "END", "GLOBAL_DIALOGUE", "GLOBAL_BOUNDARY"}:
            continue
        if n == "F4":
            total += int(costs.get("flow_step", 2))
        elif n.startswith("F"):
            total += int(costs.get("flow_step", 2))
        elif str(n).startswith("op::"):
            total += 1
        elif str(n).startswith("branch::"):
            total += 1
        elif n in costs:
            total += int(costs[n])
        elif n == "CLOSING":
            total += int(costs.get("CLOSING", 1))
        else:
            total += 1

    total += int(settings.persona_turn_extra.get(persona.value, 0))

    prof = profile_path(path)
    if persona == PersonaType.QUESTIONING and prof.has_faq:
        total += 1
    if persona == PersonaType.RESISTANT and prof.has_objection:
        total += 2
    if persona == PersonaType.IGNORANT and prof.has_faq:
        total += 1
    if PROBE_D10_DRIVE in nodes or PROBE_D9_BUSY in nodes:
        total += 2

    floor = max(int(settings.default_max_turns), int(path.base_max_turns or 0))
    # Branched long paths: cap plan budget tighter than linear retention flows.
    if any(str(n).startswith(("branch::", "op::")) for n in nodes):
        floor = min(floor, max(int(settings.default_max_turns), len(nodes) + 6))
    return min(int(settings.max_turns_absolute), max(floor, total))


def match_contradictory_personas_for_path(path: EnumeratedPath) -> List[Tuple[PersonaType, str]]:
    """Personas that semantically conflict with this path (control group candidates)."""
    matched_ids = {p.value for p, _ in match_personas_for_path(path)}
    out: List[Tuple[PersonaType, str]] = []
    for persona in PersonaType:
        if persona.value in matched_ids:
            continue
        skip, reason = should_skip(path, persona)
        if skip:
            out.append((persona, reason))
    return out


def _match_reason_for_persona(path: EnumeratedPath, persona: PersonaType) -> str:
    for pt, reason in match_personas_for_path(path):
        if pt == persona:
            return reason
    return ""


def build_cartesian_execution_plans(
    paths: List[EnumeratedPath],
    variable_values: dict[str, str] | None = None,
) -> Tuple[List[ExecutionPlan], dict]:
    """Full path × persona cartesian product; annotate semantically weak pairs."""
    vv = {str(k): str(v) for k, v in (variable_values or {}).items()}
    plans: List[ExecutionPlan] = []
    annotated_contradictions: List[dict] = []
    matrix_total = len(paths) * len(PersonaType)

    for path in paths:
        for persona in PersonaType:
            skip, conflict_reason = should_skip(path, persona)
            match_reason = _match_reason_for_persona(path, persona)
            if skip:
                plan_group = "potential_contradiction"
                reason = f"potential_contradiction:{conflict_reason}"
                annotated_contradictions.append(
                    {
                        "plan_id": f"{path.path_id}:{persona.value}",
                        "path_id": path.path_id,
                        "persona_type": persona.value,
                        "path_tags": sorted(profile_path(path).tags),
                        "reason": conflict_reason,
                        "plan_group": plan_group,
                    }
                )
            else:
                plan_group = "semantic_match"
                reason = f"semantic_match:{match_reason or '路径×全角色覆盖'}"
            mt = estimate_plan_max_turns(path, persona)
            plans.append(
                ExecutionPlan(
                    plan_id=f"{path.path_id}:{persona.value}",
                    path=path,
                    persona_type=persona.value,
                    variable_values=vv,
                    max_turns=mt,
                    reason=reason,
                    plan_group=plan_group,
                )
            )

    semantic_n = sum(1 for p in plans if p.plan_group == "semantic_match")
    contradiction_n = len(plans) - semantic_n
    meta = {
        "coverage_mode": "full_cartesian",
        "plans_matrix_total": matrix_total,
        "plans_before_filter": matrix_total,
        "plans_after_filter": len(plans),
        "skipped_count": 0,
        "skipped_plans": [],
        "semantic_plan_total": semantic_n,
        "potential_contradiction_total": contradiction_n,
        "annotated_contradictions": annotated_contradictions,
        "control_plan_total": 0,
    }
    return plans, meta


def build_semantic_execution_plans(
    paths: List[EnumeratedPath],
    variable_values: dict[str, str] | None = None,
) -> Tuple[List[ExecutionPlan], dict]:
    """Legacy alias: semantic filtering removed; returns full cartesian plans."""
    return build_cartesian_execution_plans(paths, variable_values)


def build_control_group_execution_plans(
    paths: List[EnumeratedPath],
    variable_values: dict[str, str] | None = None,
) -> Tuple[List[ExecutionPlan], dict]:
    """Run semantically contradictory path×persona pairs as control group."""
    vv = {str(k): str(v) for k, v in (variable_values or {}).items()}
    plans: List[ExecutionPlan] = []
    matrix_total = len(paths) * len(PersonaType)

    for path in paths:
        for persona, conflict_reason in match_contradictory_personas_for_path(path):
            mt = estimate_plan_max_turns(path, persona)
            plans.append(
                ExecutionPlan(
                    plan_id=f"{path.path_id}:{persona.value}:control",
                    path=path,
                    persona_type=persona.value,
                    variable_values=vv,
                    max_turns=mt,
                    reason=f"control_contradictory:{conflict_reason}",
                    plan_group="control_contradictory",
                )
            )

    meta = {
        "coverage_mode": "control_contradictory",
        "plans_matrix_total": matrix_total,
        "plans_before_filter": matrix_total,
        "plans_after_filter": len(plans),
        "skipped_count": 0,
        "skipped_plans": [],
        "semantic_plan_total": 0,
        "control_plan_total": len(plans),
    }
    return plans, meta


def build_execution_plans(
    paths: List[EnumeratedPath],
    variable_values: dict[str, str] | None = None,
    *,
    include_control_group: bool = False,
) -> Tuple[List[ExecutionPlan], dict]:
    """
    Full path × persona cartesian product.
    include_control_group is ignored (legacy); contradictions are annotated only.
    """
    plans, meta = build_cartesian_execution_plans(paths, variable_values)
    if include_control_group:
        meta = {**meta, "include_control_group_ignored": True}
    return plans, meta


def filter_compatible_plans(plans: List[ExecutionPlan]) -> Tuple[List[ExecutionPlan], dict]:
    """Legacy filter for cartesian plans; prefer build_semantic_execution_plans."""
    kept: List[ExecutionPlan] = []
    skipped: List[dict] = []
    for plan in plans:
        skip, reason = should_skip(plan.path, plan.persona_type)
        if skip:
            skipped.append(
                {
                    "plan_id": plan.plan_id,
                    "path_id": plan.path.path_id,
                    "persona_type": plan.persona_type,
                    "reason": reason,
                }
            )
            continue
        kept.append(plan)
    return kept, {
        "skipped_count": len(skipped),
        "skipped_plans": skipped,
        "plans_before_filter": len(plans),
        "plans_after_filter": len(kept),
    }


def estimate_cartesian_plan_total(paths: List[EnumeratedPath]) -> int:
    return len(paths) * len(PersonaType)


def estimate_semantic_plan_total(paths: List[EnumeratedPath]) -> int:
    """Plan count for full path×persona matrix (legacy name)."""
    return estimate_cartesian_plan_total(paths)


def estimate_control_plan_total(paths: List[EnumeratedPath]) -> int:
    return sum(len(match_contradictory_personas_for_path(p)) for p in paths)


def estimate_combined_plan_total(paths: List[EnumeratedPath], *, include_control_group: bool) -> int:
    return estimate_cartesian_plan_total(paths)
