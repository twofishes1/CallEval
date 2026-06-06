from eval1.layer2.action_detector import ActionDetector, detect_actual_action


def test_comply_with_followup_question_advances_flow():
    action = detect_actual_action("好的，能开始配送。多日合同签多久？")
    assert action == "comply"


def test_echo_question_with_na_is_ask_not_comply():
    det = ActionDetector()
    r = det.detect_sync("明白了，那我得多接单？")
    assert r.action == "ask_question"


def test_simple_ack_with_question_mark_stays_comply():
    det = ActionDetector()
    r = det.detect_sync("好的，行吗？")
    assert r.action == "comply"
