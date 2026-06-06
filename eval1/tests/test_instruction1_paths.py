# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.faq_step_context import faq_interrupt_flow_step
from eval1.layer1.instruction_capabilities import instruction_has_flow_branches, instruction_has_retention_rails
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.path_enumerator import PathEnumerator
from eval1.layer1.path_linear_curator import FAQ_ATTACH_STEPS, OOB_ATTACH_STEPS
from eval1.layer1.path_probe import PROBE_D9_BUSY, PROBE_D10_DRIVE
from eval1.layer1.rule_graph import RuleGraphBuilder


async def _parse_row(idx: int):
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    return await InstructionParserAgent().parse(f"instruction_{idx+1}", str(df.iloc[idx].iloc[-1]))


def test_instruction1_balanced_path_count():
    inst = asyncio.run(_parse_row(0))
    assert instruction_has_retention_rails(inst)
    assert not instruction_has_flow_branches(inst)
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    # mainline + 5 K-specific FAQ + OOB×3 + retain variants ≈ 18–22
    assert 16 <= len(paths) <= 24, f"expected 16-24 retention paths, got {len(paths)}"


def test_instruction1_knowledge_path_coverage():
    inst = asyncio.run(_parse_row(0))
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    kid_set = {k.id for k in (inst.knowledge_nodes or [])}
    covered = {p.target_knowledge_id for p in paths if p.target_knowledge_id}
    assert kid_set <= covered, f"missing K paths: {sorted(kid_set - covered)}"


def test_instruction1_no_inst2_probes():
    inst = asyncio.run(_parse_row(0))
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    all_nodes = [n for p in paths for n in p.nodes]
    assert PROBE_D9_BUSY not in all_nodes
    assert PROBE_D10_DRIVE not in all_nodes


def test_instruction1_faq_and_oob_coverage():
    inst = asyncio.run(_parse_row(0))
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    faq_steps = {faq_interrupt_flow_step(p.nodes) for p in paths if "FAQ_NORMAL" in p.nodes}
    for step in FAQ_ATTACH_STEPS:
        assert step in faq_steps, f"missing FAQ after {step}"
    oob_steps = set()
    for p in paths:
        if "FAQ_OOB" not in p.nodes:
            continue
        idx = p.nodes.index("FAQ_OOB")
        for n in reversed(p.nodes[:idx]):
            if n.startswith("F"):
                oob_steps.add(n)
                break
    for step in OOB_ATTACH_STEPS:
        assert step in oob_steps, f"missing OOB after {step}"


def test_instruction1_retention_scenarios():
    inst = asyncio.run(_parse_row(0))
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    assert any("F3_RETAIN" in p.nodes and "F4" in p.nodes and "OBJ_FINAL" not in p.nodes for p in paths)
    assert sum(1 for p in paths if "OBJ_FINAL" in p.nodes) >= 4


def test_instruction1_knowledge_labels_in_path_and_fsm():
    inst = asyncio.run(_parse_row(0))
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    k_paths = [p for p in paths if p.target_knowledge_id]
    assert k_paths
    for p in k_paths:
        assert p.knowledge_target_label
        assert p.target_knowledge_id in p.category_label
        assert p.target_knowledge_id in p.path_sequence_display
        assert p.target_knowledge_id in (p.node_labels.get("FAQ_NORMAL") or "")
        assert p.target_knowledge_id in p.flow_description

    from eval1.layer1.fsm_viz_builder import build_path_fsm_projection

    sample = k_paths[0]
    proj = build_path_fsm_projection(
        list(sample.nodes),
        sample.node_labels,
        gb,
        target_knowledge_id=sample.target_knowledge_id,
        instruction=inst,
    )
    faq = next(n for n in proj["nodes"] if n["id"] == "FAQ_NORMAL")
    assert sample.target_knowledge_id in faq["label"]
    assert faq.get("knowledge_id") == sample.target_knowledge_id
    faq_edge = next(e for e in proj["edges"] if e["to"] == "FAQ_NORMAL")
    assert sample.target_knowledge_id in faq_edge["label"]


def test_instruction1_mainline_is_clean():
    inst = asyncio.run(_parse_row(0))
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    main = paths[0].nodes
    assert main == ["START", "F1", "F2", "F3", "F4", "CLOSING", "END"]
