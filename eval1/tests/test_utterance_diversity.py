from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.utterance_diversity import (
    build_diversity_prompt_block,
    check_utterance_variety,
)


def test_rejects_exact_repeat():
    persona = PERSONA_REGISTRY[PersonaType.IMPATIENT]
    history = ["能跑，今天就干！"]
    reason = check_utterance_variety("能跑，今天就干！", history, persona=persona)
    assert "完全相同" in reason


def test_rejects_same_opener_across_turns():
    persona = PERSONA_REGISTRY[PersonaType.RESISTANT]
    history = ["行吧先试试", "行吧知道了", "行吧可以"]
    reason = check_utterance_variety("行吧再说吧", history, persona=persona)
    assert "句首" in reason


def test_diversity_prompt_uses_persona_role_not_phrase_bank():
    persona = PERSONA_REGISTRY[PersonaType.RESISTANT]
    block = build_diversity_prompt_block(
        ["先试试", "今天能跑"],
        persona=persona,
        turn_index=3,
    )
    assert persona.emotion_description in block
    assert persona.system_prompt_fragment in block
    assert "勿复读" in block
    assert "还有事吗" not in block


def test_variety_allows_different_wording():
    persona = PERSONA_REGISTRY[PersonaType.IMPATIENT]
    history = ["能跑，今天就干！"]
    reason = check_utterance_variety("成，记下了。", history, persona=persona)
    assert reason == ""
