# -*- coding: utf-8 -*-
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.user_simulator import UserSimulatorAgent


def test_validation_retry_higher_on_path_driven():
    sim = UserSimulatorAgent()
    assert sim._validation_retry_limit(True) >= 4
    assert sim._validation_retry_limit(False) >= 3


def test_ensure_action_alignment_does_not_replace_llm_text():
    sim = UserSimulatorAgent()
    persona = PERSONA_REGISTRY[PersonaType.COOPERATIVE]
    raw = "排名这块我记住了，恶劣天气我也尽量上线。"
    assert (
        sim._ensure_action_alignment(raw, "confirm", persona=persona, path_driven=True)
        == raw
    )


def test_api_retry_limit_allows_llm_recovery():
    sim = UserSimulatorAgent()
    assert sim._api_retry_limit() >= 2
