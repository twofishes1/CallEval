from eval1.layer2.goal_fsm import GoalFSM


def test_goal_fsm_advance():
    fsm = GoalFSM(path_nodes=["START", "F1", "END"])
    fsm.advance()
    assert fsm.current_state == "F1"
