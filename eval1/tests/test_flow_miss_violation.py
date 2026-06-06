from eval1.layer2.goal_fsm import FLOW_COVERAGE_VIOLATION_THRESHOLD
from eval1.pipeline.runner import _attach_flow_miss_violation


def test_flow_miss_attached_before_scoring_not_duplicated():
    dialogue = {"flow_adherence_rate": 0.75, "messages": ["a", "b"], "violations": []}
    _attach_flow_miss_violation(dialogue, "P10")
    assert len(dialogue["violations"]) == 1
    v = dialogue["violations"][0]
    assert v["violation_type"] == "flow_miss"
    assert v["constraint_id"] == "P10"
    assert v["deduction"] == 5.0

    _attach_flow_miss_violation(dialogue, "P10")
    assert len(dialogue["violations"]) == 1


def test_flow_miss_skipped_at_full_coverage():
    dialogue = {"flow_adherence_rate": 1.0, "messages": [], "violations": []}
    _attach_flow_miss_violation(dialogue, "P1")
    assert dialogue["violations"] == []


def test_flow_miss_skipped_above_violation_threshold():
    dialogue = {
        "flow_adherence_rate": FLOW_COVERAGE_VIOLATION_THRESHOLD + 0.01,
        "messages": [],
        "violations": [],
    }
    _attach_flow_miss_violation(dialogue, "P1")
    assert dialogue["violations"] == []
