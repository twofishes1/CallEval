# -*- coding: utf-8 -*-
"""Minimal coverage path set for instruction_2."""
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.faq_step_context import faq_interrupt_flow_step
from eval1.layer1.path_coverage_builder import FAQ_ATTACH_STEPS
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.path_coverage_builder import (
    build_minimal_coverage_paths,
    path_dedupe_key,
    uncovered_branches,
)
from eval1.layer1.path_enumerator import PathEnumerator
from eval1.layer1.path_probe import PROBE_D10_DRIVE, PROBE_D9_BUSY
from eval1.layer1.rule_graph import RuleGraphBuilder


async def _parse_instruction_2():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[1].iloc[-1])
    return await InstructionParserAgent().parse("instruction_2", raw)


def _path_identity_key(path_item) -> tuple:
    nodes = path_item.nodes if hasattr(path_item, "nodes") else path_item
    target_k = getattr(path_item, "target_knowledge_id", "") or ""
    target_d = getattr(path_item, "target_scenario_id", "") or ""
    return (tuple(nodes), target_k, target_d)


def test_all_branches_covered_without_duplicates():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    raw = [p.nodes for p in paths]
    assert not uncovered_branches(gb, raw)
    keys = [_path_identity_key(p) for p in paths]
    assert len(keys) == len(set(keys))


def test_faq_per_flow_step():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = [p.nodes for p in PathEnumerator(gb).enumerate_paths()]
    faq_steps = set()
    for p in paths:
        if "FAQ_NORMAL" in p:
            faq_steps.add(faq_interrupt_flow_step(p))
    for step in FAQ_ATTACH_STEPS:
        assert step in faq_steps, f"missing FAQ path after {step}"


def test_probes_and_oob_present():
    inst = asyncio.run(_parse_instruction_2())
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    nodes = [n for p in paths for n in p.nodes]
    assert PROBE_D9_BUSY in nodes
    assert PROBE_D10_DRIVE in nodes
    assert "FAQ_OOB" in nodes


def test_path_count_is_balanced_not_tiny():
    inst = asyncio.run(_parse_instruction_2())
    paths = build_minimal_coverage_paths(RuleGraphBuilder.build_from_instruction(inst))
    assert len(paths) >= 34, f"expected balanced set with K FAQ paths, got {len(paths)}"
    assert len(paths) <= 50
