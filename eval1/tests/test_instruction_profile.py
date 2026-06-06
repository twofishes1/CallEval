# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.instruction_profile import build_instruction_profile, build_fallback_phrase_pool
from eval1.layer2.persona import PersonaType


async def _parse_row(idx: int):
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[idx]
    raw = str(row.iloc[-1])
    did = str(row.get("dataset_id") or idx + 1)
    return await InstructionParserAgent().parse(f"instruction_{did}", raw)


def test_profile_infers_delivery_domain_for_instruction_1():
    inst = asyncio.run(_parse_row(0))
    profile = build_instruction_profile(inst, {"rider_name": "张伟"})
    assert "delivery" in profile.active_domains
    assert "配送" in profile.forbidden_phrases or "直播" in profile.forbidden_phrases
    assert profile.user_role == "骑手"


def test_profile_infers_live_domain_for_instruction_2():
    inst = asyncio.run(_parse_row(1))
    profile = build_instruction_profile(inst, {})
    assert "education_live" in profile.active_domains
    assert "配送" in profile.forbidden_phrases
    assert "骑手" in profile.forbidden_phrases
    assert profile.user_role == "培训机构/校区负责人"


def test_fallback_pool_uses_instruction_topics_not_hardcoded_task():
    inst = asyncio.run(_parse_row(1))
    profile = build_instruction_profile(inst, {})
    pool = build_fallback_phrase_pool("comply", PersonaType.COOPERATIVE, profile)
    blob = " ".join(pool)
    assert "配送" not in blob
    assert "接单" not in blob
    assert "今天的单" not in blob
    assert any("负责人" in line or "听" in line or "说明" in line for line in pool)


def test_closing_wish_from_profile_not_dataset_id():
    inst = asyncio.run(_parse_row(1))
    profile = build_instruction_profile(inst, {})
    assert profile.closing_wish == "发课顺利"
    inst1 = asyncio.run(_parse_row(0))
    profile1 = build_instruction_profile(inst1, {})
    assert profile1.closing_wish == "配送顺利"
