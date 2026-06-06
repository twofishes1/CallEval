import pytest

from eval1.layer2.action_detector import ActionDetector, ActionResult
from eval1.layer2.dialogue_trace import DialogueTrace, TurnTrace
from eval1.layer2.robust_llm import RobustLLMCall
from eval1.layer2.system_health import SystemHealthMetrics
from eval1.layer3.scoring_config import ScoringConfig


def test_action_detector_reject_high_confidence():
    det = ActionDetector()
    r = det.detect_sync("这规定太苛刻，不太想签")
    assert r.action == "reject"
    assert r.confidence >= 0.9


def test_action_detector_unknown_without_keywords():
    det = ActionDetector()
    r = det.detect_sync("……", default="")
    assert r.action == "unknown"
    assert r.needs_review is True


@pytest.mark.asyncio
async def test_action_detector_async_unknown_holds_fsm():
    det = ActionDetector()
    r = await det.detect("……", context={"fsm_state": "F1"})
    assert r.action == "unknown"
    assert r.to_fsm_action() == "unknown"


def test_dialogue_trace_records_unknown():
    trace = DialogueTrace(dialogue_id="d1", plan_id="p1")
    trace.append(
        TurnTrace(
            turn_index=1,
            fsm_state_before="F1",
            fsm_state_after="F1",
            user_utterance="嗯",
            detected_action="unknown",
            action_confidence=0.25,
        )
    )
    d = trace.to_dict()
    assert d["unknown_action_count"] == 1
    assert d["turns"][0]["detected_action"] == "unknown"


def test_scoring_config_single_judge():
    cfg = ScoringConfig()
    assert cfg.get_judge_count() == 1
    assert cfg.get_judge_count(skip=True) == 0
    assert abs(cfg.weight_sum - 1.0) < 1e-6
    assert cfg.grade_for_score(85.0) == "B"


def test_scoring_weights_normalize_to_one():
    cfg = ScoringConfig(weight_rule=0.4, weight_llm=0.5)
    assert abs(cfg.weight_sum - 1.0) < 1e-6
    assert abs(cfg.weight_rule - 0.4 / 0.9) < 1e-6


def test_aggregator_weighted_sum():
    from eval1.layer3.aggregator import Aggregator

    cfg = ScoringConfig(weight_rule=0.4, weight_llm=0.6)
    out = Aggregator().aggregate(80.0, 90.0, scoring=cfg)
    assert out["total_score"] == round(80 * 0.4 + 90 * 0.6, 2)


def test_system_health_metrics():
    records = [
        {"path_covered": True, "unknown_action_count": 0, "trace_turn_count": 4, "degraded_call_count": 0, "consistency_kappa": 0.9},
        {"path_covered": False, "unknown_action_count": 2, "trace_turn_count": 5, "degraded_call_count": 1, "consistency_kappa": 0.8, "termination_reason": "plan_timeout"},
    ]
    h = SystemHealthMetrics.from_dialogue_records(records)
    assert h.total_dialogues == 2
    assert h.path_coverage_success_rate == 0.5
    assert h.action_detection_unknown_rate == round(2 / 9, 3)


@pytest.mark.asyncio
async def test_robust_llm_degrades_on_failure():
    caller = RobustLLMCall(component="test")

    async def _fail():
        raise RuntimeError("boom")

    val, status = await caller.call_with_fallback(
        primary_fn=_fail,
        fallback_value="fallback",
        validator=lambda s: bool(s),
        max_retry=1,
        timeout=2.0,
    )
    assert val == "fallback"
    assert status == "degraded"
    assert caller.drain_degraded() == ["test"]
