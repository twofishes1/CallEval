# -*- coding: utf-8 -*-
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.persona_phrasing import (
    build_minimal_action_utterance,
    is_canned_minimal_utterance,
)


def test_reject_fallback_differs_by_persona():
    coop = PERSONA_REGISTRY[PersonaType.COOPERATIVE]
    resist = PERSONA_REGISTRY[PersonaType.RESISTANT]
    c = build_minimal_action_utterance("reject", persona=coop, turn=0)
    r = build_minimal_action_utterance("reject", persona=resist, turn=0)
    assert c != r
    assert "这规则有点苛刻" not in c


def test_canned_detector_flags_generic_lines():
    assert not is_canned_minimal_utterance("这规则有点苛刻。")
    assert is_canned_minimal_utterance("行，我先了解一下。")


def test_instruction2_fallback_no_delivery_jargon():
    import asyncio
    from pathlib import Path

    import pandas as pd

    from eval1.layer1.parser_agent import InstructionParserAgent
    from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType

    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[1]
    raw = str(row.iloc[-1])
    inst = asyncio.run(InstructionParserAgent().parse("instruction_2", raw))
    coop = PERSONA_REGISTRY[PersonaType.COOPERATIVE]
    line = build_minimal_action_utterance("comply", persona=coop, turn=0, instruction=inst)
    assert "单" not in line or "课程" in line or "说明" in line
    assert "配送" not in line
    assert "接单" not in line
    assert "跑" not in line or "跑题" in line


def test_context_prefers_continuous_day_line():
    import asyncio
    from pathlib import Path

    import pandas as pd

    from eval1.layer1.parser_agent import InstructionParserAgent

    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    inst = asyncio.run(InstructionParserAgent().parse("instruction_1", str(df.iloc[0].iloc[-1])))
    resist = PERSONA_REGISTRY[PersonaType.RESISTANT]
    line = build_minimal_action_utterance(
        "reject",
        persona=resist,
        turn=0,
        last_bot_utterance="单日合同需要连续3天完成配送。",
        instruction=inst,
    )
    assert "连续" in line or "三天" in line or "排" in line or "签" in line or "关于" in line
