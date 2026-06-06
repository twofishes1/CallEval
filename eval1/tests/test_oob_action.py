# -*- coding: utf-8 -*-
from eval1.layer2.action_detector import ActionDetector, is_oob_scope_question
from eval1.layer2.goal_fsm import GoalFSM


def test_is_oob_scope_question_app_status():
    assert is_oob_scope_question("对了，App 里哪里看合同状态？")


def test_oob_question_classified_off_topic():
    det = ActionDetector()
    r = det.detect_sync("对了，App 里哪里看合同状态？")
    assert r.action == "off_topic"


def test_f2_ask_oob_advances_to_faq_oob_on_path():
    path = ["START", "F1", "F2", "FAQ_OOB", "CLOSING", "END"]
    fsm = GoalFSM.from_path(path)
    fsm.try_transition("comply")
    fsm.try_transition("comply")
    tr = fsm.try_transition("off_topic")
    assert tr.moved and tr.to_state == "FAQ_OOB"
