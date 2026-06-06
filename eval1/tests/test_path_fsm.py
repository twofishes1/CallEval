"""Path-driven GoalFSM: Layer1 path → FSM transitions."""

from eval1.layer2.goal_fsm import GoalFSM

STANDARD = ["START", "F1", "F2", "F3", "F4", "CLOSING", "END"]
RETENTION = ["START", "F1", "OBJECTION", "F3_RETAIN", "F2", "F3", "F4", "CLOSING", "END"]
FAQ_PATH = ["START", "F1", "FAQ_NORMAL", "F2", "F3", "F4", "CLOSING", "END"]


def test_standard_path_comply_advances_flow():
    fsm = GoalFSM.from_path(STANDARD)
    assert fsm.current_state == "START"
    tr = fsm.try_transition("comply")
    assert tr.moved and tr.to_state == "F1"
    tr = fsm.try_transition("comply")
    assert tr.to_state == "F2"
    tr = fsm.try_transition("comply")
    assert tr.to_state == "F3"


def test_standard_path_reject_not_on_path():
    fsm = GoalFSM.from_path(STANDARD)
    fsm.try_transition("comply")  # F1
    tr = fsm.try_transition("reject")
    assert not tr.moved and tr.reason == "reject_not_on_path"
    assert fsm.current_state == "F1"


def test_retention_path_reject_goes_to_objection():
    fsm = GoalFSM.from_path(RETENTION)
    fsm.try_transition("comply")  # F1
    tr = fsm.try_transition("reject")
    assert tr.moved and tr.to_state == "OBJECTION"


def test_retention_retain_success_resumes_main_flow():
    fsm = GoalFSM.from_path(RETENTION)
    fsm.try_transition("comply")  # F1
    fsm.try_transition("reject")  # OBJECTION
    fsm.try_transition("reject")  # F3_RETAIN
    tr = fsm.try_transition("comply", retain_success=True)
    assert tr.moved and tr.to_state == "F2"


def test_faq_path_ask_question():
    fsm = GoalFSM.from_path(FAQ_PATH)
    fsm.try_transition("comply")  # F1
    tr = fsm.try_transition("ask_question")
    assert tr.moved and tr.to_state == "FAQ_NORMAL"
    tr = fsm.try_transition("comply")
    assert tr.to_state == "F2"


def test_reject_limit_to_obj_final():
    path = ["START", "F1", "OBJECTION", "F3_RETAIN", "OBJ_FINAL", "END"]
    fsm = GoalFSM.from_path(path)
    fsm.try_transition("comply")
    fsm.try_transition("reject")
    fsm.try_transition("reject")
    tr = fsm.try_transition("reject", consecutive_reject=3, reject_limit=3)
    assert tr.to_state == "OBJ_FINAL"


def test_reject_limit_not_from_f1():
    """First reject at F1 should enter retention, not skip to OBJ_FINAL."""
    path = ["START", "F1", "F3_RETAIN", "OBJ_FINAL", "END"]
    fsm = GoalFSM.from_path(path)
    fsm.try_transition("comply")
    tr = fsm.try_transition("reject", consecutive_reject=1, reject_limit=1)
    assert tr.moved and tr.to_state == "F3_RETAIN"


def test_comply_at_f1_holds_on_retention_only_path():
    path = ["START", "F1", "F3_RETAIN", "OBJ_FINAL", "END"]
    fsm = GoalFSM.from_path(path)
    fsm.try_transition("comply")
    tr = fsm.try_transition("comply")
    assert not tr.moved and tr.reason == "comply_hold_before_reject"
    assert fsm.current_state == "F1"


def test_comply_skips_f3_retain_to_f4():
    path = ["START", "F1", "F2", "F3", "F3_RETAIN", "F4", "CLOSING", "END"]
    fsm = GoalFSM.from_path(path)
    for _ in range(3):
        fsm.try_transition("comply")
    assert fsm.current_state == "F3"
    tr = fsm.try_transition("comply")
    assert tr.moved and tr.to_state == "F4"


def test_allowed_actions_no_reject_on_standard():
    fsm = GoalFSM.from_path(STANDARD)
    fsm.try_transition("comply")
    assert "reject" not in fsm.get_allowed_user_actions()


def test_is_goal_achieved_only_at_end():
    fsm = GoalFSM.from_path(STANDARD)
    assert not fsm.is_goal_achieved()
    while not fsm.is_terminal():
        fsm.try_transition("comply")
    assert fsm.is_goal_achieved()


def test_flow_rate_credits_opening_as_f1():
    fsm = GoalFSM.from_path(STANDARD)
    rate = fsm.get_flow_adherence_rate(
        ["START"],
        bot_action_log=["T1:opening_line:START"],
    )
    assert rate >= 1 / 6


def test_flow_rate_skips_unvisited_faq_branch():
    fsm = GoalFSM.from_path(FAQ_PATH)
    rate = fsm.get_flow_adherence_rate(
        ["START", "F1", "F2", "F3", "F4", "CLOSING", "END"],
        bot_action_log=[
            "T1:opening_line:START",
            "T2:step_response:F1",
            "T3:step_response:F2",
            "T4:step_response:F3",
            "T5:f4_part:F4",
            "T6:step_response:CLOSING",
        ],
    )
    assert rate == 1.0


def test_flow_rate_uses_bot_log_when_fsm_undercounts():
    path = ["START", "F1", "F2", "F3", "F3_RETAIN", "F4", "CLOSING", "END"]
    fsm = GoalFSM.from_path(path)
    rate = fsm.get_flow_adherence_rate(
        ["F3_RETAIN", "F4", "CLOSING"],
        bot_action_log=[
            "T1:opening_line:START",
            "T2:step_response:F3_RETAIN",
            "T3:f4_part:F4",
            "T4:step_response:CLOSING",
        ],
    )
    assert rate >= 0.66
