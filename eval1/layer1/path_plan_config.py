from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from eval1.layer1.instruction_capabilities import instruction_has_flow_branches, instruction_has_retention_rails
from eval1.layer1.rule_graph import RuleGraphBuilder

PathPlanMode = Literal["linear", "branched"]


@dataclass(frozen=True)
class PathPlanConfig:
    """
    Task-agnostic coverage plan for Layer1 path enumeration.

    All tasks share the same pipeline stages; only these knobs differ per instruction.
    """

    mode: PathPlanMode
    faq_attach_steps: tuple[str, ...]
    oob_attach_steps: tuple[str, ...]
    include_probes: bool
    include_retention_variants: bool
    max_paths: int

    @property
    def is_branched(self) -> bool:
        return self.mode == "branched"

    @property
    def is_linear(self) -> bool:
        return self.mode == "linear"


def _flow_step_nodes(gb: RuleGraphBuilder) -> tuple[str, ...]:
    return tuple(n for n in (gb.flow_nodes or []) if str(n).startswith("F"))


def infer_path_plan_config(gb: RuleGraphBuilder, *, max_paths: int = 64) -> PathPlanConfig:
    """
    Derive coverage plan from instruction capabilities + graph shape.

    - Branched (instruction_2): branch-grid + FAQ on extended steps + single OOB + probes.
    - Linear + retention (instruction_1): DFS pool + curator selectors + FAQ/OOB on F2–F4 + probes.
    """
    inst = gb.instruction
    branched = instruction_has_flow_branches(inst)
    retention = instruction_has_retention_rails(inst)
    flow_steps = _flow_step_nodes(gb)

    if branched:
        # FAQ after knowledge-heavy steps; OOB once before rule explanation (F4).
        faq_steps = tuple(s for s in ("F2", "F3", "F4", "F5", "F7") if s in flow_steps)
        oob_steps = ("F4",) if "F4" in flow_steps else ()
    else:
        # Linear flow: FAQ/OOB can attach after any post-opening step.
        faq_steps = tuple(s for s in flow_steps if s not in {"F1"})
        oob_steps = faq_steps

    return PathPlanConfig(
        mode="branched" if branched else "linear",
        faq_attach_steps=faq_steps,
        oob_attach_steps=oob_steps,
        include_probes=True,
        include_retention_variants=retention,
        max_paths=max_paths,
    )
