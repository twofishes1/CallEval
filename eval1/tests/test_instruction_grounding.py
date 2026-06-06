from eval1.layer1.models import Constraint, ConstraintType, KnowledgeNode, ParsedInstruction
from eval1.layer2.instruction_grounding import (
    build_deterministic_grounded_reply,
    build_instruction_grounding,
    is_grounded_in_instruction,
    match_instruction_snippets,
)


def _sample_instruction() -> ParsedInstruction:
    return ParsedInstruction(
        instruction_id="t1",
        raw_text="",
        role_description="站长",
        task_description="通知飞毛腿合同",
        opening_line="你好，我是站长。午餐和晚餐高峰期需要上线。单日至少 **X 单**。",
        flow_steps=[
            "告知骑手今天飞毛腿合同已生效，并询问他们是否可以开始配送。",
            "说明单日飞毛腿合同需要连续 Y 天完成配送；否则合同将受到影响。",
        ],
        constraints=[
            Constraint(
                id="B1",
                type=ConstraintType.BOUNDARY,
                text='如被问及超出职责范围的问题，回复："我向同事确认后再回电给你。我现在能回答的先回答。"',
            )
        ],
        knowledge_nodes=[
            KnowledgeNode(id="K1", text="单日合同：在生效当天必须完成 X 单，否则合同及派单可能受到影响。", trigger_type="on_user_ask"),
            KnowledgeNode(id="K2", text="如果你无法连续配送 Y 天，你的名额可能会被他人占用。", trigger_type="on_user_ask"),
        ],
        variables={},
    )


def test_peak_hour_question_does_not_allow_invented_times():
    inst = _sample_instruction()
    grounding = build_instruction_grounding(inst, {"X": "5", "Y": "3"})
    bad = "高峰期是11点到13点、17点到19点。合同今天已生效，能开始配送不？"
    assert not is_grounded_in_instruction(bad, grounding)


def test_peak_hour_question_matches_opening_not_faq_times():
    inst = _sample_instruction()
    grounding = build_instruction_grounding(inst, {"X": "5", "Y": "3"})
    matched = match_instruction_snippets("高峰期具体几点？", grounding)
    assert any("午餐和晚餐高峰期" in s for s in matched)
    reply = build_deterministic_grounded_reply(
        question="高峰期具体几点？",
        grounding=grounding,
        current_step_text=inst.flow_steps[0],
    )
    assert "11" not in reply and "13" not in reply
    assert is_grounded_in_instruction(reply, grounding)


def test_unknown_question_uses_boundary_phrase():
    inst = _sample_instruction()
    grounding = build_instruction_grounding(inst, {"X": "5", "Y": "3"})
    reply = build_deterministic_grounded_reply(
        question="今天会下雨吗？",
        grounding=grounding,
        current_step_text=inst.flow_steps[0],
    )
    assert "同事确认" in reply
