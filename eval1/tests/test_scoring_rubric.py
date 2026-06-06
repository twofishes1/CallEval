from eval1.layer3.judge_types import DimensionJudgeScore, JudgeResult
from eval1.layer3.retention_context import (
    analyze_retention_context,
    apply_retention_scoring_policy,
    instruction_supports_retention,
)
from eval1.layer3.rubrics import compute_weighted_llm_score, score_1_to_100
from eval1.layer3.llm_judge import LLMJudge
from eval1.layer2.instruction_injection import (
    f4_coverage_summary,
    update_f4_delivery,
    F4_PART_META,
)


def test_score_1_to_100():
    assert score_1_to_100(5) == 100.0
    assert score_1_to_100(3) == 60.0


def test_compute_weighted_llm_score():
    scores = {d: 4 for d in ("flow_adherence", "dialogue_compliance", "knowledge_accuracy", "retention_effectiveness", "boundary_handling", "naturalness")}
    assert compute_weighted_llm_score(scores) == 80.0


def test_compute_weighted_skips_na_dimension():
    scores = {d: 4 for d in ("flow_adherence", "dialogue_compliance", "knowledge_accuracy", "retention_effectiveness", "boundary_handling", "naturalness")}
    assert compute_weighted_llm_score(scores, skip_dims={"retention_effectiveness"}) == 80.0


class _Inst:
    def __init__(self, task="", flow_steps=None):
        self.task = task
        self.flow_steps = flow_steps or []
        self.constraints = []
        self.knowledge_nodes = []


def test_instruction_2_has_no_retention():
    inst = _Inst(task="告知直播产品升级", flow_steps=["身份确认", "告知升级", "确认知情"])
    assert instruction_supports_retention(inst) is False


def test_instruction_1_has_retention():
    inst = _Inst(flow_steps=["F1", "F2", "挽留不想配送的骑手"])
    assert instruction_supports_retention(inst) is True


def test_retention_not_applicable_for_live_upgrade_task():
    inst = _Inst(task="直播升级通知", flow_steps=["身份确认", "告知升级"])
    dialogue = {
        "messages": [{"turn": 1, "role": "bot", "content": "你好"}],
        "covered_nodes": ["START", "F1", "F2"],
        "trace": {"turns": []},
    }
    ctx = analyze_retention_context(dialogue, inst)
    assert ctx["retention_applicable"] is False
    assert ctx["retention_required"] is False

    result = JudgeResult(
        dimensions=[
            DimensionJudgeScore(
                dimension="retention_effectiveness",
                score=2,
                reasoning="",
                evidence_turns=[],
                key_issues=["missing_turn_evidence"],
                weight=0.15,
            )
        ],
        overall_comment="",
        top_improvement="",
        total_score=30.0,
    )
    fixed = apply_retention_scoring_policy(result, ctx)
    ret = next(d for d in fixed.dimensions if d.dimension == "retention_effectiveness")
    assert ret.applicable is False
    assert ret.weight == 0.0
    assert "missing_turn_evidence" not in ret.key_issues
    assert "任务不适用" in ret.reasoning


def test_llm_judge_parse_payload():
    judge = LLMJudge()
    payload = {
        "dimensions": [
            {
                "dimension": "flow_adherence",
                "score": 4,
                "reasoning": "[T2] Bot说明合同生效",
                "evidence_turns": [2],
                "key_issues": [],
            },
            {
                "dimension": "dialogue_compliance",
                "score": 3,
                "reasoning": "[T3] 话术基本合规",
                "evidence_turns": [3],
                "key_issues": [],
            },
            {
                "dimension": "knowledge_accuracy",
                "score": 4,
                "reasoning": "[T4] 变量正确",
                "evidence_turns": [4],
                "key_issues": [],
            },
            {
                "dimension": "retention_effectiveness",
                "score": 3,
                "reasoning": "[T5] 有挽留",
                "evidence_turns": [5],
                "key_issues": [],
            },
            {
                "dimension": "boundary_handling",
                "score": 5,
                "reasoning": "[T6] 边界清晰",
                "evidence_turns": [6],
                "key_issues": [],
            },
            {
                "dimension": "naturalness",
                "score": 4,
                "reasoning": "[T7] 较自然",
                "evidence_turns": [7],
                "key_issues": [],
            },
        ],
        "overall_comment": "ok",
        "top_improvement": "F4",
    }
    result = judge._parse_judge_payload(payload, degraded=False)
    assert result.total_score == 75.0
    assert len(result.dimensions) == 6
    assert result.dimensions[0].evidence_turns == [2]


def test_llm_judge_caps_score_without_evidence():
    judge = LLMJudge()
    payload = {
        "dimensions": [
            {"dimension": d, "score": 5, "reasoning": "无轮次", "evidence_turns": [], "key_issues": []}
            for d in (
                "flow_adherence",
                "dialogue_compliance",
                "knowledge_accuracy",
                "retention_effectiveness",
                "boundary_handling",
                "naturalness",
            )
        ],
    }
    result = judge._parse_judge_payload(payload, degraded=False)
    assert all(d.score <= 2 for d in result.dimensions)


def test_retention_not_required_on_cooperative_path():
    dialogue = {
        "messages": [
            {"turn": 1, "role": "bot", "content": "你好"},
            {"turn": 2, "role": "user", "content": "好的，可以"},
        ],
        "covered_nodes": ["START", "F1", "F2", "F3", "F4", "CLOSING", "END"],
        "trace": {"turns": [{"turn_index": 2, "detected_action": "comply", "fsm_state_before": "F1", "fsm_state_after": "F2"}]},
    }
    ctx = analyze_retention_context(dialogue)
    assert ctx["retention_required"] is False

    low_retention = JudgeResult(
        dimensions=[
            DimensionJudgeScore(
                dimension="retention_effectiveness",
                score=2,
                reasoning="缺乏挽留",
                evidence_turns=[7],
                key_issues=["缺乏有效挽留策略"],
                weight=0.15,
            )
        ],
        overall_comment="",
        top_improvement="",
        total_score=30.0,
    )
    fixed = apply_retention_scoring_policy(low_retention, ctx)
    ret = next(d for d in fixed.dimensions if d.dimension == "retention_effectiveness")
    assert ret.score == 4
    assert "不适用" in ret.reasoning


def test_retention_required_when_user_rejects():
    dialogue = {
        "messages": [{"turn": 3, "role": "user", "content": "不太想签，太苛刻"}],
        "covered_nodes": ["START", "F1", "OBJECTION"],
        "trace": {"turns": [{"turn_index": 3, "detected_action": "reject", "fsm_state_after": "OBJECTION"}]},
    }
    ctx = analyze_retention_context(dialogue)
    assert ctx["retention_required"] is True


def test_f4_coverage_tracking():
    from eval1.layer2.instruction_injection import advance_f4_speech_index, build_f4_single_utterance

    state = {"f4_speech_index": 0}
    line = build_f4_single_utterance(
        "说明飞毛腿报名是按排名进行的，并非站长干预。"
        "骑手应减少拒单、取消和超时。在恶劣天气下工作、订单量更高，有助于保住飞毛腿资格。"
    )
    update_f4_delivery(state, line)
    advance_f4_speech_index(state)
    cov = f4_coverage_summary(state)
    assert "ranking" in cov["delivered"]
    assert cov["complete"] is True
    assert len(F4_PART_META) == 3
