# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer2.user_sim_instruction_context import build_user_sim_scene


async def _parse_row(idx: int):
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[idx]
    import json

    slots_raw = row.get("variable_values", "{}")
    slots = json.loads(str(slots_raw)) if str(slots_raw).strip() not in ("", "nan") else {}
    raw = str(row.iloc[-1])
    did = str(row.get("dataset_id") or row.get("id") or idx + 1)
    return await InstructionParserAgent().parse(f"instruction_{did}", raw, slots)


def test_instruction1_user_scene_is_rider():
    inst = asyncio.run(_parse_row(0))
    scene = build_user_sim_scene(inst, {"rider_name": "张伟"})
    assert scene.user_role == "骑手"
    assert scene.caller_label == "站长"
    assert "配送" in scene.task_summary or "飞毛腿" in scene.task_summary
    assert "骑手" in scene.scene_block
    assert "站长" in scene.scene_block


def test_instruction2_user_scene_forbids_delivery_jargon():
    inst = asyncio.run(_parse_row(1))
    scene = build_user_sim_scene(inst, {})
    assert "配送" in scene.forbidden_phrases
    assert scene.user_role == "培训机构/校区负责人"
    assert "告知机构" not in scene.task_summary
    assert "等对方说明" in scene.task_summary


def test_instruction2_parses_role_and_task():
    inst = asyncio.run(_parse_row(1))
    assert "Customer Support" in inst.role_description or "Support" in inst.role_description
    assert "直播" in inst.task_description
