from eval1.layer1.models import Constraint, ConstraintType, KnowledgeNode, ParsedInstruction
from eval1.layer2.instruction_injection import (
    EVAL_MODE_TAG,
    build_bot_system_prompt,
    check_instruction_completeness,
    substitute_variables,
)
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.user_directive import get_user_directive


def test_substitute_variables():
    text = "单日至少${X}单，${rider_name}请确认"
    out = substitute_variables(text, {"X": "5", "rider_name": "张伟"})
    assert "5" in out and "张伟" in out


def test_check_instruction_completeness_warns_missing():
    inst = ParsedInstruction(
        instruction_id="t1",
        raw_text="",
        role_description="站长",
        task_description="",
        opening_line="",
        flow_steps=[],
        constraints=[],
        knowledge_nodes=[],
        variables={},
    )
    warnings = check_instruction_completeness(inst)
    assert any("Task" in w for w in warnings)
    assert any("Call Flow" in w for w in warnings)


def test_build_bot_system_prompt_includes_eval_mode():
    inst = ParsedInstruction(
        instruction_id="t1",
        raw_text="",
        resolved_text="## Role\n站长\n\n## Task\n外呼",
        role_description="站长",
        task_description="外呼",
        opening_line="你好",
        flow_steps=["确认配送"],
        constraints=[Constraint(id="D1", type=ConstraintType.DIALOGUE, text="30字")],
        knowledge_nodes=[KnowledgeNode(id="K1", text="FAQ1", trigger_type="on_user_ask")],
        variables={},
    )
    prompt, warnings = build_bot_system_prompt(inst, {"X": "5"})
    assert EVAL_MODE_TAG in prompt
    assert "站长" in prompt
    assert warnings == []


def test_get_user_directive_objection():
    persona = PERSONA_REGISTRY[PersonaType.RESISTANT]
    d = get_user_directive(
        current_state="OBJECTION",
        persona=persona,
        allowed_actions=["reject", "ask_question", "comply"],
        required_action="resolve_objection",
    )
    assert "OBJECTION" in d or "规则" in d
    assert "禁止" in d
