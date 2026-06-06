from eval1.layer2.goal_fsm import GoalFSM
from eval1.layer2.path_user_driver import infer_path_user_action, next_path_node


def test_standard_path_user_complies_to_f2():
    fsm = GoalFSM.from_path(["START", "F1", "F2", "F3", "F4", "CLOSING", "END"])
    fsm.try_transition("comply")  # -> F1
    action, nxt, _ = infer_path_user_action(fsm)
    assert nxt == "F2"
    assert action == "comply"


def test_faq_path_user_asks_question():
    fsm = GoalFSM.from_path(["START", "F1", "FAQ_NORMAL", "F2", "CLOSING", "END"])
    fsm.try_transition("comply")  # F1
    action, nxt, hint = infer_path_user_action(fsm)
    assert nxt == "FAQ_NORMAL"
    assert action == "ask_question"
    assert "追问" in hint


def test_at_faq_user_complies_to_resume():
    fsm = GoalFSM.from_path(["START", "F1", "FAQ_NORMAL", "F2", "CLOSING", "END"])
    fsm.try_transition("comply")
    fsm.try_transition("ask_question")
    action, nxt, _ = infer_path_user_action(fsm)
    assert fsm.current_state == "FAQ_NORMAL"
    assert nxt == "F2"
    assert action == "comply"


def test_retention_path_user_rejects():
    fsm = GoalFSM.from_path(["START", "F1", "F3_RETAIN", "F2", "CLOSING", "END"])
    fsm.try_transition("comply")
    action, nxt, _ = infer_path_user_action(fsm)
    assert nxt == "F3_RETAIN"
    assert action == "reject"


def test_oob_path_user_off_topic():
    fsm = GoalFSM.from_path(["START", "F1", "FAQ_OOB", "CLOSING", "END"])
    fsm.try_transition("comply")
    action, nxt, _ = infer_path_user_action(fsm)
    assert nxt == "FAQ_OOB"
    assert action == "off_topic"


def test_next_path_node():
    fsm = GoalFSM.from_path(["START", "F1", "F2", "END"])
    assert next_path_node(fsm) == "F1"
