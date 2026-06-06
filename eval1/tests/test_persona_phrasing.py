from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.user_context_memory import UserContextMemory
from eval1.layer2.user_simulator_prompt import build_user_sim_system_prompt, build_user_sim_user_prompt


def test_system_prompt_is_adaptive_not_phrase_bank():
    persona = PERSONA_REGISTRY[PersonaType.RESISTANT]
    ctx = UserContextMemory()
    ctx.absorb_bot_snippets(["需连续3天配送"])
    ctx.update_from_user("连续三天太苛刻", "reject")
    prompt = build_user_sim_system_prompt(
        persona,
        rider_name="张伟",
        context=ctx,
        current_state="F2",
        allowed_actions=["comply"],
        required_action="advance_flow",
        questions_at_step=0,
        messages=[{"role": "bot", "content": "要连续3天哦"}],
        sampled_action="comply",
        path_user_action="comply",
    )
    assert "自主措辞" in prompt
    assert "上下文记忆" in prompt
    assert "你仍有顾虑" in prompt
    assert "F2" not in prompt
    assert "下一项呢" not in prompt
    assert persona.emotion_description in prompt


def test_user_prompt_uses_memory_position():
    persona = PERSONA_REGISTRY[PersonaType.IMPATIENT]
    ctx = UserContextMemory()
    ctx.absorb_bot_snippets(["单日5单"])
    prompt = build_user_sim_user_prompt(
        persona=persona,
        context=ctx,
        sampled_action="comply",
        turn_index=2,
        last_bot_utterance="请确认连续跑满3天",
        has_prior_bot=True,
        current_state="F2",
        user_history=["能跑。"],
    )
    assert "站长刚说" in prompt
    assert "对话位置" in prompt
    assert persona.system_prompt_fragment in prompt
    assert "勿复读" in prompt
