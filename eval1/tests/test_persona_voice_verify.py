from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.persona_phrasing import (
    build_minimal_action_utterance,
    verify_persona_tone,
)


def test_soft_persona_verify_allows_varied_phrasing():
    p = PERSONA_REGISTRY[PersonaType.IMPATIENT]
    assert verify_persona_tone("知道了，现在能开始了吗？", p, sampled_action="comply")
    assert verify_persona_tone("行，说重点。", p, sampled_action="comply")


def test_reject_cannot_say_comply_markers():
    p = PERSONA_REGISTRY[PersonaType.COOPERATIVE]
    assert not verify_persona_tone("没问题，可以开始配送。", p, sampled_action="reject")


def test_minimal_pool_rotates():
    a = build_minimal_action_utterance("comply", turn=0, user_history=[])
    b = build_minimal_action_utterance("comply", turn=1, user_history=[a])
    assert a != b
