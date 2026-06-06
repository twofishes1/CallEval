# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.instruction_flow_normalizer import normalize_flow_and_knowledge
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.preprocessor import InstructionPreprocessor


async def _parse_row(idx: int):
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[idx]
    import json

    slots_raw = row.get("variable_values", "{}")
    slots = json.loads(str(slots_raw)) if str(slots_raw).strip() not in ("", "nan") else {}
    raw = str(row.iloc[-1])
    return await InstructionParserAgent().parse(f"instruction_{idx+1}", raw, slots)


def test_instruction1_keeps_four_main_steps():
    inst = asyncio.run(_parse_row(0))
    assert len(inst.flow_steps) == 4
    assert len(inst.knowledge_nodes) >= 5


def test_instruction2_main_steps_not_forty_one():
    inst = asyncio.run(_parse_row(1))
    assert 5 <= len(inst.flow_steps) <= 10
    assert len(inst.knowledge_nodes) >= 5


def test_normalizer_extracts_faq_from_flow_body():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[1].iloc[-1])
    prep = InstructionPreprocessor().preprocess(raw)
    raw_flow = prep["sections"]["call_flow"]
    main, knowledge = normalize_flow_and_knowledge(raw_flow, [])
    assert any("低延迟" in k or "标准直播" in k for k in knowledge)
    assert len(main) < len(raw_flow)
    assert not any("→" in k and k.strip().startswith("若") for k in knowledge)
    assert not any("进入第" in k and k.strip().startswith("若") for k in knowledge)


def test_instruction2_knowledge_excludes_branch_lines():
    inst = asyncio.run(_parse_row(1))
    for k in inst.knowledge_nodes:
        assert "→" not in k.text or not k.text.strip().startswith("若"), k.text[:40]
