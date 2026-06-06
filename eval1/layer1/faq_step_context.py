from __future__ import annotations

import re
from typing import Any, List, Sequence, Tuple

from eval1.layer2.instruction_injection import substitute_variables

# Fallback for branched tasks (instruction_2); linear tasks use infer_faq_step_knowledge().
FAQ_STEP_KNOWLEDGE: dict[str, Tuple[str, ...]] = {
    "F2": ("K2", "K4", "K5"),
    "F3": ("K3", "K4", "K5", "K6"),
    "F4": ("K7", "K8", "K9", "K10"),
    "F5": ("K11", "K12"),
    "F7": ("K13", "K14"),
}


def infer_faq_step_knowledge(
    instruction: Any | None,
    faq_attach_steps: Sequence[str],
) -> dict[str, Tuple[str, ...]]:
    """
    Map each knowledge node (K*) to an FAQ attach flow step.
    Used by Layer1 to emit one FAQ path per K (linear / task1).
    """
    steps = tuple(s for s in faq_attach_steps if s)
    if not steps:
        return dict(FAQ_STEP_KNOWLEDGE)

    kids: List[str] = []
    for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
        kid = str(getattr(kn, "id", "") if not isinstance(kn, dict) else kn.get("id", ""))
        if kid.startswith("K"):
            kids.append(kid)
    if not kids:
        return {s: FAQ_STEP_KNOWLEDGE.get(s, ()) for s in steps if FAQ_STEP_KNOWLEDGE.get(s)}

    buckets: dict[str, List[str]] = {s: [] for s in steps}
    for i, kid in enumerate(kids):
        buckets[steps[i % len(steps)]].append(kid)
    return {s: tuple(v) for s, v in buckets.items() if v}


def faq_path_desc_tag(desc: str) -> str:
    """Parse target K id from path item desc, e.g. faq_after_f2@K3 -> K3."""
    if "@" not in str(desc or ""):
        return ""
    tag = str(desc).rsplit("@", 1)[-1].strip()
    return tag if tag.startswith("K") else ""


def knowledge_seed_for_id(instruction: Any | None, kid: str, slots: dict[str, str] | None = None) -> str:
    if not instruction or not kid:
        return ""
    slots = dict(slots or {})
    for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
        if str(getattr(kn, "id", "") if not isinstance(kn, dict) else kn.get("id", "")) != kid:
            continue
        text = substitute_variables(str(getattr(kn, "text", kn)), slots)
        return _seed_from_knowledge_text(text)
    return ""


def faq_interrupt_flow_step(path_nodes: Sequence[str]) -> str:
    """Flow step (F*) that FAQ_NORMAL follows in this path."""
    nodes = list(path_nodes or [])
    if "FAQ_NORMAL" not in nodes:
        return ""
    idx = nodes.index("FAQ_NORMAL")
    for n in reversed(nodes[:idx]):
        if str(n).startswith("F") and len(n) > 1 and n[1:].isdigit():
            return str(n)
        if str(n).startswith("branch::"):
            parts = str(n).split("::")
            if len(parts) > 1 and parts[1].isdigit():
                return f"F{parts[1]}"
        if str(n).startswith("op::"):
            parts = str(n).split("::")
            if len(parts) > 1 and parts[1].isdigit():
                return f"F{parts[1]}"
    return "F2"


def _seed_from_knowledge_text(text: str) -> str:
    t = re.sub(r"\*\*", "", str(text or "")).strip()
    t = re.sub(r"^(参考话术|询问)[:：]\s*", "", t)
    if "？" in t or "?" in t:
        return t.split("？")[0].split("?")[0].strip() + "？"
    if len(t) > 24:
        return t[:24] + "…？"
    return (t + "？") if t and not t.endswith(("？", "?")) else t


def ask_seeds_for_faq_step(
    instruction: Any | None,
    flow_step: str,
    slots: dict[str, str] | None = None,
    *,
    target_knowledge_id: str = "",
) -> Tuple[str, ...]:
    if not instruction or not flow_step:
        return ()
    slots = dict(slots or {})
    if target_knowledge_id:
        seed = knowledge_seed_for_id(instruction, target_knowledge_id, slots)
        return (seed,) if seed else ()

    attach_steps = tuple(
        s for s in ("F2", "F3", "F4", "F5", "F7") if s == flow_step or flow_step.startswith("F")
    )
    step_map = infer_faq_step_knowledge(instruction, attach_steps or (flow_step,))
    want = set(step_map.get(flow_step, ()) or FAQ_STEP_KNOWLEDGE.get(flow_step, ()))
    seeds: List[str] = []
    for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
        kid = str(getattr(kn, "id", ""))
        if want and kid not in want:
            continue
        text = substitute_variables(str(getattr(kn, "text", kn)), slots)
        seed = _seed_from_knowledge_text(text)
        if seed and seed not in seeds:
            seeds.append(seed)
    if not seeds and want:
        for fq in list(getattr(instruction, "faq_nodes", []) or []):
            q = str(getattr(fq, "question", fq) if not isinstance(fq, dict) else fq.get("question", "")).strip()
            if q and q not in seeds:
                seeds.append(q if q.endswith(("？", "?")) else f"{q}？")
                if len(seeds) >= 2:
                    break
    return tuple(seeds[:4])
