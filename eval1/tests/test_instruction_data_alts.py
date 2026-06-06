# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.instruction_grounding import (
    build_objection_reply_hint,
    build_step_utterance_alts,
    match_instruction_snippets,
)
from eval1.layer2.instruction_injection import compress_f4_step_to_utterance


async def _load_data_instruction():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[0]
    import json

    slots = json.loads(str(row["variable_values"]))
    raw = str(row.iloc[-1])
    return await InstructionParserAgent().parse("instruction_1", raw, slots), slots


def test_f4_compress_derived_from_data_flow_step():
    step4 = (
        "说明飞毛腿报名是按排名进行的，并非站长干预。"
        "骑手应减少拒单、取消和超时。在恶劣天气下工作、订单量更高，有助于保住飞毛腿资格。"
    )
    line = compress_f4_step_to_utterance(step4, slots={"Y": "3"})
    assert "排名" in line
    assert "拒单" in line


def test_step_alts_from_data_instruction():
    import asyncio

    inst, slots = asyncio.run(_load_data_instruction())
    f4_text = inst.flow_steps[3]
    alts = build_step_utterance_alts(inst, "F4", f4_text, slots)
    assert len(alts) >= 2
    joined = " ".join(alts)
    assert "排名" in joined or "站长" in joined


def test_ranking_objection_matches_faq_from_data():
    import asyncio

    inst, slots = asyncio.run(_load_data_instruction())
    from eval1.layer2.instruction_grounding import build_instruction_grounding

    grounding = build_instruction_grounding(inst, slots)
    matched = match_instruction_snippets("不想靠运气混口饭吃", grounding)
    assert matched


def test_objection_hint_cites_constraints_and_faq():
    import asyncio

    inst, slots = asyncio.run(_load_data_instruction())
    from eval1.layer2.instruction_grounding import build_instruction_grounding

    grounding = build_instruction_grounding(inst, slots)
    hint = build_objection_reply_hint(
        instruction=inst,
        grounding=grounding,
        question="不想靠运气混口饭吃",
        current_state="F4",
        current_step_text=inst.flow_steps[3],
    )
    assert "重复" in hint or "重申" in hint
    assert "FAQ" in hint or "Knowledge" in hint or "名额" in hint
