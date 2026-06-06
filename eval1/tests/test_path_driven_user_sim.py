from eval1.layer2.goal_fsm import GoalFSM
from eval1.layer2.path_user_driver import infer_path_user_action, path_coverage_action
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.user_simulator import UserSimulatorAgent


def test_path_coverage_action_faq_and_retain():
    assert path_coverage_action("ask_question", "advance_flow", ["comply", "ask_question"]) == "ask_question"
    assert path_coverage_action("reject", "advance_flow", ["comply", "reject"]) == "reject"
    assert path_coverage_action("comply", "advance_flow", ["comply", "reject"]) is None


def test_cooperative_persona_samples_reject_on_retention_path():
    fsm = GoalFSM.from_path(["START", "F1", "F3_RETAIN", "OBJ_FINAL", "END"])
    fsm.try_transition("comply")
    action, _, _ = infer_path_user_action(fsm)
    assert action == "reject"
    sim = UserSimulatorAgent()
    persona = PERSONA_REGISTRY[PersonaType.COOPERATIVE]
    sampled = sim._sample_action(
        persona,
        "advance_flow",
        ["comply", "ask_question", "reject", "off_topic"],
        path_user_action=action,
    )
    assert sampled == "reject"


def test_cooperative_persona_samples_ask_on_faq_path():
    fsm = GoalFSM.from_path(["START", "F1", "F2", "FAQ_NORMAL", "F3", "CLOSING", "END"])
    fsm.try_transition("comply")
    fsm.try_transition("comply")
    action, nxt, _ = infer_path_user_action(fsm)
    assert nxt == "FAQ_NORMAL"
    assert action == "ask_question"
    sim = UserSimulatorAgent()
    persona = PERSONA_REGISTRY[PersonaType.COOPERATIVE]
    sampled = sim._sample_action(
        persona,
        "advance_flow",
        ["comply", "ask_question", "reject", "off_topic"],
        path_user_action=action,
    )
    assert sampled == "ask_question"
