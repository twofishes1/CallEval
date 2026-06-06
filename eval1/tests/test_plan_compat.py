from eval1.layer1.models import EnumeratedPath
from eval1.layer2.persona import PersonaType
from eval1.pipeline.plan_compat import (
    build_cartesian_execution_plans,
    build_control_group_execution_plans,
    build_execution_plans,
    estimate_cartesian_plan_total,
    estimate_control_plan_total,
    estimate_plan_max_turns,
    match_contradictory_personas_for_path,
    match_personas_for_path,
    profile_path,
    should_skip,
)
from eval1.pipeline.planner import ExecutionPlanner, estimate_semantic_plan_total


def _mainline_path(path_id: str = "P1") -> EnumeratedPath:
    return EnumeratedPath(
        path_id=path_id,
        nodes=["START", "F1", "F2", "F3", "F4", "CLOSING", "END"],
        activated_rules=["F1"],
        base_max_turns=20,
        description="main",
    )


def _faq_path() -> EnumeratedPath:
    return EnumeratedPath(
        path_id="P2",
        nodes=["START", "F1", "F2", "F3", "FAQ_NORMAL", "F4", "CLOSING", "END"],
        activated_rules=["F1"],
        base_max_turns=24,
        description="faq",
    )


def _retain_path() -> EnumeratedPath:
    return EnumeratedPath(
        path_id="P3",
        nodes=["START", "F1", "OBJECTION", "F3_RETAIN", "F2", "F3", "F4", "CLOSING", "END"],
        activated_rules=["F1"],
        base_max_turns=28,
        description="retain",
    )


def test_profile_mainline():
    assert profile_path(_mainline_path()).is_mainline


def test_match_mainline_personas():
    matched = match_personas_for_path(_mainline_path())
    ids = {p.value for p, _ in matched}
    assert ids == {PersonaType.COOPERATIVE.value, PersonaType.IMPATIENT.value}


def test_match_faq_personas():
    matched = match_personas_for_path(_faq_path())
    ids = {p.value for p, _ in matched}
    assert ids == {p.value for p in PersonaType}
    assert PersonaType.COOPERATIVE.value in ids


def test_match_retain_personas():
    matched = match_personas_for_path(_retain_path())
    ids = {p.value for p, _ in matched}
    assert ids == {PersonaType.RESISTANT.value}


def test_should_skip_questioning_on_mainline():
    skip, reason = should_skip(_mainline_path(), PersonaType.QUESTIONING)
    assert skip is True
    assert "FAQ" in reason


def test_cartesian_plans_full_matrix():
    paths = [_mainline_path(), _faq_path(), _retain_path()]
    plans, meta = build_cartesian_execution_plans(paths)
    assert meta["plans_matrix_total"] == 18
    assert len(plans) == 18
    assert meta["coverage_mode"] == "full_cartesian"
    assert meta["semantic_plan_total"] + meta["potential_contradiction_total"] == 18
    assert estimate_cartesian_plan_total(paths) == 18
    assert estimate_semantic_plan_total(paths) == 18


def test_planner_returns_cartesian_meta():
    plans, meta = ExecutionPlanner().plan([_mainline_path(), _faq_path()])
    assert len(plans) == 12
    assert meta["coverage_mode"] == "full_cartesian"


def test_max_turns_objection_higher_than_mainline():
    main = estimate_plan_max_turns(_mainline_path(), PersonaType.COOPERATIVE)
    retain = estimate_plan_max_turns(_retain_path(), PersonaType.RESISTANT)
    assert retain > main


def test_max_turns_f4_path_uses_single_flow_step_budget():
    faq = estimate_plan_max_turns(_faq_path(), PersonaType.QUESTIONING)
    assert faq >= 20


def test_contradictory_personas_on_mainline():
    matched = match_contradictory_personas_for_path(_mainline_path())
    ids = {p.value for p, _ in matched}
    assert PersonaType.QUESTIONING.value in ids
    assert PersonaType.COOPERATIVE.value not in ids


def test_control_group_builder_legacy():
    paths = [_mainline_path(), _faq_path(), _retain_path()]
    control, meta = build_control_group_execution_plans(paths)
    assert meta["control_plan_total"] == 9
    assert len(control) == 9
    assert all(p.plan_group == "control_contradictory" for p in control)
    assert estimate_control_plan_total(paths) == 9


def test_build_execution_plans_ignores_control_flag():
    paths = [_mainline_path(), _faq_path(), _retain_path()]
    plans, meta = build_execution_plans(paths, include_control_group=True)
    assert meta["coverage_mode"] == "full_cartesian"
    assert len(plans) == 18
    assert meta.get("include_control_group_ignored") is True
