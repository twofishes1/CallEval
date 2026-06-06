# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.dst import DST
from eval1.layer2.goal_fsm import GoalFSM
from eval1.layer2.mandatory_scripts import (
    get_mandatory_bot_utterance,
    infer_branch_user_hint,
    is_mandatory_script_exempt,
)
from eval1.layer2.path_user_driver import infer_path_user_action


async def _parse_instruction_2():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[1].iloc[-1])
    return await InstructionParserAgent().parse("instruction_2", raw)


def test_f4_publish_ask_complete_not_truncated():
    inst = asyncio.run(_parse_instruction_2())
    bot_state: dict = {}
    line = get_mandatory_bot_utterance(inst, "F4", bot_state)
    assert line
    assert "Web控制台" in line
    assert "校务系统" in line
    assert "SaaS" in line
    assert "发课" in line
    assert len(line.replace(" ", "")) >= 25
    assert is_mandatory_script_exempt(line)
    assert bot_state.get("mandatory:f4_publish_ask")
    assert get_mandatory_bot_utterance(inst, "F4", bot_state) == ""


def test_f2_delivers_step1_ref_then_ask():
    inst = asyncio.run(_parse_instruction_2())
    bot_state: dict = {}
    ref = get_mandatory_bot_utterance(inst, "F2", bot_state)
    assert ref
    assert "低延迟" in ref or "升级" in ref
    ask = get_mandatory_bot_utterance(inst, "F2", bot_state)
    assert ask
    assert "标准直播" in ask or "知道吗" in ask


def test_dst_exempts_mandatory_f4_ask():
    inst = asyncio.run(_parse_instruction_2())
    line = get_mandatory_bot_utterance(inst, "F4", {})
    dst = DST()
    violations = dst.check_constraints(
        line,
        turn_index=2,
        instruction=inst,
        fsm=GoalFSM.from_path(["F4"]),
        is_mandatory_script=True,
    )
    assert not any(v["violation_type"] == "dialogue_length" for v in violations)


def test_branch_user_hint_web_visible():
    nodes = ["F4", "branch::4::Web控制台::1", "F5"]
    hint = infer_branch_user_hint(nodes, current_state="F4")
    assert "Web" in hint
    assert "已" in hint or "看到" in hint


def test_branch_user_hint_third_party_hidden():
    nodes = ["F4", "branch::4::第三方系统::4", "F5"]
    hint = infer_branch_user_hint(nodes, current_state="F4")
    assert "第三方" in hint or "校务" in hint or "SaaS" in hint
    assert "还没" in hint or "未" in hint


def test_path_user_driver_f4_branch_hint():
    nodes = [
        "START",
        "F1",
        "branch::1::main::1",
        "F2",
        "branch::2::main::1",
        "F3",
        "F4",
        "branch::4::Web控制台::2",
        "F5",
    ]
    fsm = GoalFSM.from_path(nodes)
    while fsm.current_state != "F4":
        fsm.try_transition("comply")
    action, nxt, hint = infer_path_user_action(fsm)
    assert action == "comply"
    assert "Web" in hint
    assert "还没" in hint or "未" in hint
