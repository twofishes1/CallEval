from eval1.layer1.models import EnumeratedPath
from eval1.pipeline.planner import ExecutionPlanner, estimate_plan_total, estimate_semantic_plan_total, select_execution_plans


def test_planner_cartesian_all_personas_per_path():
    p = EnumeratedPath(
        path_id="P1",
        nodes=["START", "F1", "F2", "F3", "F4", "CLOSING", "END"],
        activated_rules=["F1", "D1"],
        base_max_turns=20,
        description="main",
    )
    plans, meta = ExecutionPlanner().plan([p])
    assert len(plans) == 6
    assert {x.persona_type for x in plans} == {
        "cooperative",
        "resistant",
        "ignorant",
        "impatient",
        "off_topic",
        "questioning",
    }
    assert meta["coverage_mode"] == "full_cartesian"
    assert all(x.max_turns >= 20 for x in plans)


def test_select_plans_defaults_to_full_cartesian_set():
    p = EnumeratedPath(
        path_id="P1",
        nodes=["START", "F1", "END"],
        activated_rules=[],
        base_max_turns=10,
        description="main",
    )
    p2 = p.model_copy(update={"path_id": "P2"})
    all_plans, _ = ExecutionPlanner().plan([p, p2])
    assert estimate_semantic_plan_total([p, p2]) == 12
    assert estimate_plan_total(2) == 12
    selected, meta = select_execution_plans(all_plans, None)
    assert len(selected) == 12
    assert meta["plans_truncated"] == 0
    capped, meta2 = select_execution_plans(all_plans, 4)
    assert len(capped) == 4
    assert meta2["plans_truncated"] == 8
