"""RuleJudge F4 checks must respect path nodes and instruction domain."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from eval1.layer1.models import EnumeratedPath, ExecutionPlan
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer3.rule_judge import RuleJudge


def _plan(nodes):
    path = EnumeratedPath(
        path_id="Px",
        nodes=nodes,
        activated_rules=["F1"],
        base_max_turns=20,
        description="test",
    )
    return ExecutionPlan(
        plan_id="Px:cooperative",
        path=path,
        persona_type="cooperative",
        variable_values={},
        max_turns=20,
    )


def _delivery_instruction():
    return SimpleNamespace(
        flow_steps=[
            "F1",
            "说明单日飞毛腿需连续3天配送",
            "F3",
            "说明飞毛腿按排名、少拒单取消超时、恶劣天气保资格",
        ],
    )


async def _parse_instruction_2():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    row = df.iloc[1]
    raw = str(row.iloc[-1])
    return await InstructionParserAgent().parse("instruction_2", raw)


def test_f4_violation_skipped_when_f4_not_on_path():
    judge = RuleJudge()
    plan = _plan(["START", "F1", "F3_RETAIN", "OBJ_FINAL", "END"])
    dialogue = {
        "violations": [],
        "flow_adherence_rate": 1.0,
        "bot_state": {"last_bot_utterance": "骑手今天飞毛腿合同已生效。"},
        "messages": [{"role": "bot", "content": "x"}] * 4,
        "opening_line_match": True,
    }
    ret = judge.score(plan, dialogue)
    assert not any(
        v.get("constraint_id") == "F4"
        for v in (ret.get("supplemental_violations") or [])
    )


def test_f4_violation_when_delivery_f4_incomplete():
    judge = RuleJudge()
    plan = _plan(["START", "F1", "F2", "F3", "F4", "CLOSING", "END"])
    dialogue = {
        "violations": [],
        "flow_adherence_rate": 1.0,
        "bot_state": {"f4_entered": True, "f4_speech_index": 0, "last_bot_utterance": "排名机制"},
        "messages": [{"role": "bot", "content": "x"}] * 6,
        "opening_line_match": True,
    }
    ret = judge.score(plan, dialogue, instruction=_delivery_instruction())
    assert any(
        v.get("constraint_id") == "F4"
        for v in (ret.get("supplemental_violations") or [])
    )


def test_f4_violation_skipped_for_instruction_2():
    judge = RuleJudge()
    inst = asyncio.run(_parse_instruction_2())
    plan = _plan(["START", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "CLOSING", "END"])
    dialogue = {
        "violations": [],
        "flow_adherence_rate": 1.0,
        "bot_state": {"f4_entered": True, "f4_speech_index": 0, "last_bot_utterance": "前端可见吗"},
        "messages": [{"role": "bot", "content": "x"}] * 6,
        "opening_line_match": True,
    }
    ret = judge.score(plan, dialogue, instruction=inst)
    assert not any(
        v.get("constraint_id") == "F4"
        for v in (ret.get("supplemental_violations") or [])
    )
