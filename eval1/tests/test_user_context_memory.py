from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.user_context_memory import UserContextMemory, merge_bot_knowledge, merge_user_turn


def test_memory_tracks_bot_facts():
    mem = UserContextMemory()
    merged = merge_bot_knowledge(mem, ["飞毛腿合同已生效", "需连续3天配送"])
    ctx = UserContextMemory.from_legacy(merged)
    assert len(ctx.bot_facts) == 2
    assert "连续" in ctx.bot_facts[1]


def test_memory_tracks_user_stance_and_concern():
    mem = UserContextMemory()
    merged = merge_user_turn(mem, "行吧，先试试，但连续三天太苛刻。", "comply")
    ctx = UserContextMemory.from_legacy(merged)
    assert ctx.user_stances
    merged2 = merge_user_turn(ctx, "这规定谁定的？不太合理。", "reject")
    ctx2 = UserContextMemory.from_legacy(merged2)
    assert ctx2.open_concerns


def test_memory_prompt_includes_persona_cooperation():
    persona = PERSONA_REGISTRY[PersonaType.RESISTANT]
    mem = UserContextMemory()
    mem.absorb_bot_snippets(["需连续3天配送"])
    mem.update_from_user("我不太想签。", "reject")
    block = mem.format_for_prompt(persona, caller_label="站长")
    assert "30%" in block or "配合倾向" in block
    assert "站长已告知" in block
    assert "顾虑" in block


def test_from_dialogue_rebuilds_stances():
    mem = UserContextMemory.from_dialogue(
        user_memory=["fact:合同已生效"],
        messages=[
            {"role": "bot", "content": "合同生效了"},
            {"role": "user", "content": "行吧，能跑。"},
        ],
        user_history=["行吧，能跑。"],
    )
    assert mem.bot_facts
    assert mem.user_stances
