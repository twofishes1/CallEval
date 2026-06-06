from __future__ import annotations



from typing import List, Tuple



from eval1.config import settings

from eval1.layer1.models import EnumeratedPath, ExecutionPlan

from eval1.layer2.persona import PersonaType

from eval1.pipeline.plan_compat import (

    build_execution_plans,

    estimate_plan_max_turns,

    estimate_semantic_plan_total,

)





def estimate_path_turn_budget(path: EnumeratedPath, persona: PersonaType | None = None) -> int:

    """Estimate bot-turn budget; uses cooperative persona as neutral baseline when omitted."""

    p = persona or PersonaType.COOPERATIVE

    return estimate_plan_max_turns(path, p)





def count_persona_types() -> int:

    return len(PersonaType)





def estimate_plan_total(path_count: int, *, persona_count: int | None = None) -> int:

    """Upper bound if using full cartesian (legacy); semantic mode uses fewer plans."""

    p = persona_count if persona_count is not None else count_persona_types()

    return max(0, int(path_count)) * max(0, int(p))





def select_execution_plans(

    all_plans: List[ExecutionPlan],

    max_plans: int | None = None,

    plan_ids: List[str] | None = None,

) -> Tuple[List[ExecutionPlan], dict[str, int]]:

    """

    Select plans to run. Default (max_plans None or <=0): all semantically matched plans.

    Positive max_plans caps count for smoke/debug runs only.

    """

    pool = list(all_plans)
    if plan_ids:
        want = {str(x).strip() for x in plan_ids if str(x).strip()}
        scenario_tags = {w[1:].upper() for w in want if w.startswith("@")}
        want -= {f"@{t}" for t in scenario_tags}
        pool = [
            p
            for p in pool
            if p.plan_id in want
            or p.path.path_id in want
            or f"{p.path.path_id}:{p.persona_type}" in want
            or (
                scenario_tags
                and str(getattr(p.path, "target_scenario_id", "") or "").upper() in scenario_tags
            )
        ]

    total = len(pool)

    if max_plans is None or int(max_plans) <= 0:

        selected = list(pool)

        cap = total

    else:

        cap = max(0, int(max_plans))

        selected = list(pool[:cap])

    meta = {

        "plans_total": total,

        "plans_selected": len(selected),

        "plans_truncated": max(0, total - len(selected)),

    }

    return selected, meta





class ExecutionPlanner:

    def plan(

        self,

        paths: List[EnumeratedPath],

        variable_values: dict[str, str] | None = None,

        *,

        include_control_group: bool = False,

    ) -> Tuple[List[ExecutionPlan], dict]:

        """Full path×persona cartesian product; semantic hints via plan_group."""

        return build_execution_plans(

            paths,

            variable_values,

            include_control_group=include_control_group,

        )


