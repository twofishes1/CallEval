# -*- coding: utf-8 -*-
from eval1.layer1.models import EvalReport, ExecutionPlan, EnumeratedPath
from eval1.pipeline.report_merge import merge_partial_rerun


def _plan(pid: str) -> ExecutionPlan:
    path = EnumeratedPath(
        path_id=pid.split(":")[0],
        nodes=["START", "F1", "END"],
        activated_rules=[],
        base_max_turns=12,
        description="",
    )
    persona = pid.split(":")[1] if ":" in pid else "cooperative"
    return ExecutionPlan(
        plan_id=pid,
        path=path,
        persona_type=persona,
        variable_values={},
        repeat_count=1,
        max_turns=12,
        reason="test",
    )


def _report(pid: str, score: float) -> EvalReport:
    return EvalReport(
        report_id=f"r-{pid}",
        plan_id=pid,
        path_id=pid.split(":")[0],
        persona_type=pid.split(":")[1] if ":" in pid else "cooperative",
        total_score=score,
        grade="A",
        rule_score=score,
        llm_score=score,
        consistency_penalty=0.0,
        flow_adherence_rate=1.0,
        total_turns=4,
        termination_reason="goal_achieved",
        violations=[],
        dimension_scores={},
        improvement_suggestions=[],
        created_at="2026-01-01T00:00:00",
        summary="",
    )


def test_merge_partial_rerun_reuses_cached():
    all_plans = [_plan("P1:cooperative"), _plan("P2:cooperative"), _plan("P36:impatient")]
    existing = {
        "reports": [
            _report("P1:cooperative", 80).model_dump(),
            _report("P2:cooperative", 70).model_dump(),
        ],
        "layer2": {
            "dialogues": [
                {"plan_id": "P1:cooperative", "messages": []},
                {"plan_id": "P2:cooperative", "messages": []},
            ]
        },
    }
    new_reports = {"P36:impatient": _report("P36:impatient", 100)}
    new_dialogues = {"P36:impatient": {"plan_id": "P36:impatient", "messages": [{"role": "bot"}]}}

    reports, dialogues, meta = merge_partial_rerun(
        all_plans=all_plans,
        rerun_plan_ids={"P36:impatient"},
        new_reports=new_reports,
        new_dialogues=new_dialogues,
        existing_payload=existing,
    )

    assert [r.plan_id for r in reports] == ["P1:cooperative", "P2:cooperative", "P36:impatient"]
    assert [d["plan_id"] for d in dialogues] == ["P1:cooperative", "P2:cooperative", "P36:impatient"]
    assert meta["plans_rerun"] == 1
    assert meta["plans_reused"] == 2
    assert reports[-1].total_score == 100


def test_completed_plan_ids():
    from eval1.pipeline.report_merge import completed_plan_ids

    payload = {"reports": [{"plan_id": "P1:cooperative"}, {"plan_id": "P2:cooperative"}]}
    assert completed_plan_ids(payload) == {"P1:cooperative", "P2:cooperative"}
    assert completed_plan_ids(None) == set()


def test_merge_partial_rerun_prefers_new_over_cache():
    all_plans = [_plan("P36:impatient")]
    existing = {
        "reports": [_report("P36:impatient", 50).model_dump()],
        "layer2": {"dialogues": [{"plan_id": "P36:impatient", "messages": []}]},
    }
    new_reports = {"P36:impatient": _report("P36:impatient", 95)}
    new_dialogues = {"P36:impatient": {"plan_id": "P36:impatient", "messages": [{"role": "user"}]}}

    reports, dialogues, meta = merge_partial_rerun(
        all_plans=all_plans,
        rerun_plan_ids={"P36:impatient"},
        new_reports=new_reports,
        new_dialogues=new_dialogues,
        existing_payload=existing,
    )

    assert reports[0].total_score == 95
    assert meta["plans_rerun"] == 1
    assert meta["plans_reused"] == 0
    assert dialogues[0]["messages"][0]["role"] == "user"
