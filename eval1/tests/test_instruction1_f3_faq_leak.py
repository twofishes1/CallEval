# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.instruction_grounding import (
    build_step_utterance_alts,
    is_faq_leak_on_flow_step,
)


async def _parse_instruction_1():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[0].iloc[-1])
    return await InstructionParserAgent().parse("instruction_1", raw)


def test_f3_alts_exclude_faq_k1():
    inst = asyncio.run(_parse_instruction_1())
    f3 = str(inst.flow_steps[2])
    alts = build_step_utterance_alts(inst, "F3", f3)
    joined = " ".join(alts)
    assert "许多骑手" not in joined
    assert "名额可能会被" not in joined


def test_f3_fallback_is_encourage_safety():
    inst = asyncio.run(_parse_instruction_1())
    f3 = str(inst.flow_steps[2])
    alts = build_step_utterance_alts(inst, "F3", f3)
    assert alts
    line = alts[0]
    assert "许多骑手" not in line
    assert any(k in line for k in ("安全", "辛苦", "加油", "配送", "注意", "挽留", "鼓励"))


def test_faq_leak_detected_on_f3_not_on_faq_node():
    assert is_faq_leak_on_flow_step("F3", "目前，许多骑手正在申请飞毛腿。")
    assert not is_faq_leak_on_flow_step("FAQ_NORMAL", "目前，许多骑手正在申请飞毛腿。")
    assert not is_faq_leak_on_flow_step("F3", "路上注意安全，能跑尽量跑。")
