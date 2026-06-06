# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.goal_fsm import GoalFSM
from eval1.layer2.instruction_profile import build_instruction_profile, pick_shell_topic
from eval1.layer2.path_user_driver import infer_path_user_action
from eval1.layer2.persona_phrasing import (
    build_minimal_action_utterance,
    is_disconnected_user_response,
    is_generic_persona_stub,
    is_listen_only_ack,
    is_questioning_hollow_confirm,
    is_resistant_overly_cooperative,
    is_role_term_misuse,
)
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType


async def _parse_instruction_1():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[0].iloc[-1])
    return await InstructionParserAgent().parse("instruction_1", raw)


def test_no_rider_role_echo_in_comply_boost():
    inst = asyncio.run(_parse_instruction_1())
    profile = build_instruction_profile(inst, {"rider_name": "张伟"})
    bot = "骑手今天飞毛腿合同已生效。"
    line = build_minimal_action_utterance(
        "comply",
        turn=0,
        persona=PersonaType.COOPERATIVE,
        last_bot_utterance=bot,
        instruction=inst,
        slot_values={"rider_name": "张伟"},
    )
    assert "骑手我" not in line.replace(" ", "")
    assert line != "行，骑手我明白了。"


def test_f4_to_closing_uses_confirm_action():
    fsm = GoalFSM.from_path(["START", "F1", "F2", "F3", "F4", "CLOSING", "END"])
    while fsm.current_state != "F4":
        fsm.try_transition("comply")
    action, nxt, hint = infer_path_user_action(fsm)
    assert nxt == "CLOSING"
    assert action == "confirm"
    assert "先听一下" in hint or "排名" in hint


def test_listen_only_ack_rejected_after_long_bot():
    bot = "飞毛腿报名是按排名进行的，并非站长干预。骑手应减少拒单、取消和超时。"
    assert is_listen_only_ack("行，我先听一下。", bot, action="confirm")
    assert not is_listen_only_ack("明白了，我会少拒单。", bot, action="confirm")


def test_generic_persona_stub_after_f4():
    bot = "飞毛腿报名是按排名进行的，并非站长干预。骑手应减少拒单、取消和超时。"
    assert is_generic_persona_stub("行，说重点。", bot, action="confirm")
    assert is_generic_persona_stub("大体明白，但还想确认一点。", bot, action="confirm")
    assert not is_generic_persona_stub("明白了，排名和拒单我会注意。", bot, action="confirm")


def test_impatient_stub_blocked():
    bot = "飞毛腿报名是按排名进行的，骑手应减少拒单、取消和超时。恶劣天气订单量更高。"
    assert is_disconnected_user_response("行，说重点。", bot)


def test_impatient_f4_confirm_shell_has_context():
    inst = asyncio.run(_parse_instruction_1())
    bot = "飞毛腿报名是按排名进行的，骑手应减少拒单、取消和超时。恶劣天气订单量更高。"
    line = build_minimal_action_utterance(
        "confirm",
        turn=0,
        persona=PersonaType.IMPATIENT,
        last_bot_utterance=bot,
        instruction=inst,
    )
    assert "说重点" not in line
    assert any(k in line for k in ("排名", "拒单", "天气", "超时"))


def test_impatient_tone_hint_requires_echo():
    from eval1.layer2.persona_phrasing import build_persona_contextual_tone_hint

    persona = PERSONA_REGISTRY[PersonaType.IMPATIENT]
    bot = "飞毛腿报名是按排名进行的，骑手应减少拒单。"
    hint = build_persona_contextual_tone_hint(
        persona, action="confirm", current_state="F4", last_bot_utterance=bot
    )
    assert "排名" in hint
    assert "说重点" in hint and "禁止" in hint


def test_questioning_f4_confirm_shell_has_context():
    inst = asyncio.run(_parse_instruction_1())
    bot = "飞毛腿报名是按排名进行的，骑手应减少拒单、取消和超时。恶劣天气订单量更高。"
    line = build_minimal_action_utterance(
        "confirm",
        turn=0,
        persona=PersonaType.QUESTIONING,
        last_bot_utterance=bot,
        instruction=inst,
    )
    assert "还想确认" not in line
    assert "大体明白" not in line
    assert any(k in line for k in ("排名", "拒单", "天气", "超时", "依据", "怎么"))


def test_questioning_hollow_confirm_blocked():
    bot = "飞毛腿报名是按排名进行的，骑手应减少拒单、取消和超时。"
    persona = PERSONA_REGISTRY[PersonaType.QUESTIONING]
    assert is_questioning_hollow_confirm("大体明白，但还想确认一点。", bot, persona, action="confirm")
    assert is_questioning_hollow_confirm("好的，明白了。", bot, persona, action="confirm")
    assert not is_questioning_hollow_confirm("排名是系统自动算的吧？", bot, persona, action="confirm")


def test_topic_terms_exclude_instruction_labels():
    inst = asyncio.run(_parse_instruction_1())
    profile = build_instruction_profile(inst, {"rider_name": "张伟"})
    assert "Role" not in profile.topic_terms
    assert "Task" not in profile.topic_terms
    assert pick_shell_topic(profile) == "飞毛腿"


def test_impatient_shell_no_role_leak():
    inst = asyncio.run(_parse_instruction_1())
    bot = "我向同事确认后再回电给你。我现在能回答的先回答。"
    line = build_minimal_action_utterance(
        "comply",
        turn=0,
        persona=PersonaType.IMPATIENT,
        last_bot_utterance=bot,
        instruction=inst,
    )
    assert "Role" not in line
    assert "Task" not in line


def test_impatient_hollow_blocked():
    from eval1.layer2.persona_phrasing import is_impatient_hollow_response

    persona = PERSONA_REGISTRY[PersonaType.IMPATIENT]
    bot = "路上注意安全，能跑尽量跑。"
    assert is_impatient_hollow_response("嗯，还有别的吗？", bot, persona, action="comply")
    assert not is_impatient_hollow_response("行，安全知道了，还有吗？", bot, persona, action="comply")


def test_questioning_tone_hint_requires_echo():
    from eval1.layer2.persona_phrasing import build_persona_contextual_tone_hint

    persona = PERSONA_REGISTRY[PersonaType.QUESTIONING]
    bot = "飞毛腿报名是按排名进行的，骑手应减少拒单。"
    hint = build_persona_contextual_tone_hint(
        persona, action="confirm", current_state="F4", last_bot_utterance=bot
    )
    assert "排名" in hint
    assert "还想确认" in hint and "禁止" in hint


def test_resistant_comply_requires_reluctant_tone():
    persona = PERSONA_REGISTRY[PersonaType.RESISTANT]
    assert is_resistant_overly_cooperative("好的，路上会小心的。", persona, action="comply")
    assert is_resistant_overly_cooperative("好的，恶劣天气我也尽量上线。", persona, action="comply")
    assert not is_resistant_overly_cooperative("行吧，会注意，但别催太紧。", persona, action="comply")
    assert not is_resistant_overly_cooperative("连续三天？要是没完成咋办？", persona, action="comply")


def test_resistant_comply_shell_has_reluctant_tone():
    inst = asyncio.run(_parse_instruction_1())
    bot = "路上注意安全，能跑尽量跑。"
    line = build_minimal_action_utterance(
        "comply",
        turn=0,
        persona=PersonaType.RESISTANT,
        last_bot_utterance=bot,
        instruction=inst,
    )
    assert "好的，路上会小心的" not in line
    assert any(k in line for k in ("行吧", "但", "看情况", "别催", "不过"))
