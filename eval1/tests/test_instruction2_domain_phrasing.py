# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.instruction_grounding import build_closing_reply_alts


async def _parse_instruction_2():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[1]
    raw = str(row.iloc[-1])
    return await InstructionParserAgent().parse("instruction_2", raw)


def test_instruction2_closing_alts_no_delivery_jargon():
    inst = asyncio.run(_parse_instruction_2())
    alts = build_closing_reply_alts(inst, "cooperative")
    blob = " ".join(alts)
    assert "接单" not in blob
    assert "配送" not in blob
    assert any("发课" in a or "联系" in a for a in alts)
