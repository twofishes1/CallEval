# -*- coding: utf-8 -*-
"""Bot F4 must not inject task-1 delivery jargon for instruction_2."""
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.instruction_injection import (
    build_f4_single_utterance,
    instruction_f4_is_delivery_split,
    pick_flow_step_utterance,
)


async def _parse_instruction_2():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[1]
    raw = str(row.iloc[-1])
    return await InstructionParserAgent().parse("instruction_2", raw)


def test_instruction2_f4_is_not_delivery_split():
    inst = asyncio.run(_parse_instruction_2())
    f4_text = str(inst.flow_steps[3])
    assert not instruction_f4_is_delivery_split(inst, f4_text)


def test_instruction2_f4_utterance_no_rider_jargon():
    inst = asyncio.run(_parse_instruction_2())
    f4_text = str(inst.flow_steps[3])
    line = build_f4_single_utterance(f4_text, instruction=inst)
    assert "飞毛腿" not in line
    assert "拒单" not in line
    assert "骑手" not in line
    assert "排名" not in line or "前端" in line


def test_instruction2_pick_flow_step_f4_uses_instruction():
    inst = asyncio.run(_parse_instruction_2())
    f4_text = str(inst.flow_steps[3])
    line = pick_flow_step_utterance("F4", f4_text, {}, instruction=inst)
    assert "飞毛腿" not in line
    assert "拒单" not in line
