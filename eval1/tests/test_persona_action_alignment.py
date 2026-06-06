from eval1.layer2.action_detector import ActionDetector
from eval1.layer2.persona_phrasing import build_minimal_action_utterance


def test_strict_verify_rejects_comply_as_reject():
    det = ActionDetector()
    assert not det.verify_for_sampled("没问题，可以开始配送。", "reject", strict=True)
    assert det.verify_for_sampled("今天先不签。", "reject", strict=True)


def test_minimal_reject_is_detected():
    from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType

    line = build_minimal_action_utterance(
        "reject", turn=0, persona=PERSONA_REGISTRY[PersonaType.RESISTANT]
    )
    det = ActionDetector().detect_sync(line)
    assert det.action == "reject"
