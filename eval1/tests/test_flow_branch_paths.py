# -*- coding: utf-8 -*-
"""Branch-aware parsing and path generation for instruction_2."""
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.flow_branch_model import branches_by_step, parse_instruction_branches
from eval1.layer1.instruction_capabilities import instruction_has_flow_branches
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.path_enumerator import PathEnumerator
from eval1.layer1.path_probe import PROBE_D10_DRIVE, PROBE_D9_BUSY
from eval1.layer1.rule_graph import RuleGraphBuilder
from eval1.pipeline.plan_compat import PersonaType, match_personas_for_path


async def _parse_instruction_2():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[1].iloc[-1])
    return await InstructionParserAgent().parse("instruction_2", raw)


def test_instruction2_has_structured_branches():
    inst = asyncio.run(_parse_instruction_2())
    assert instruction_has_flow_branches(inst)
    by_step = branches_by_step(inst.raw_text)
    assert len(by_step.get(1, [])) >= 2
    assert len(by_step.get(4, [])) >= 4
    assert len(by_step.get(5, [])) >= 2, f"F5 branches: {by_step.get(5)}"
    assert len(by_step.get(6, [])) >= 2


def test_f5_branches_include_fee_paths():
    inst = asyncio.run(_parse_instruction_2())
    f5 = branches_by_step(inst.raw_text)[5]
    conds = " ".join(b.condition for b in f5)
    assert "费用" in conds


def test_f4_branches_have_sections():
    inst = asyncio.run(_parse_instruction_2())
    f4 = branches_by_step(inst.raw_text)[4]
    sections = {b.section for b in f4 if b.section}
    assert any("Web" in s or "控制台" in s for s in sections)
    assert any("第三方" in s or "系统" in s for s in sections)


def test_f4_third_party_hidden_has_op_chain():
    inst = asyncio.run(_parse_instruction_2())
    f4 = branches_by_step(inst.raw_text)[4]
    guided = [b for b in f4 if b.op_steps]
    assert len(guided) >= 1
    assert len(guided[0].op_steps) >= 3


def test_no_direct_f4_to_f5_when_branched():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    assert not gb.g.has_edge("F4", "F5")


def test_p1_prefers_cooperative_mainline_without_faq():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    p1 = paths[0]
    assert "FAQ_NORMAL" not in p1.nodes
    matched = {p.value for p, _ in match_personas_for_path(p1)}
    assert PersonaType.COOPERATIVE.value in matched
    branch_nodes = [n for n in p1.nodes if str(n).startswith("branch::")]
    assert branch_nodes


def test_paths_cover_f6_wechat_branches():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    wechat_conds = set()
    for p in paths:
        for n in p.nodes:
            if str(n).startswith("branch::6::"):
                wechat_conds.add(n)
    assert len(wechat_conds) >= 2


def test_instruction2_knowledge_path_coverage():
    inst = asyncio.run(_parse_instruction_2())
    paths = PathEnumerator(RuleGraphBuilder.build_from_instruction(inst)).enumerate_paths()
    kid_set = {k.id for k in (inst.knowledge_nodes or [])}
    covered = {p.target_knowledge_id for p in paths if p.target_knowledge_id}
    assert kid_set <= covered, f"missing K paths: {sorted(kid_set - covered)}"


def test_instruction2_scenario_and_k_labels():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    k_paths = [p for p in paths if p.target_knowledge_id]
    assert k_paths
    for p in k_paths:
        assert p.knowledge_target_label
        assert p.target_knowledge_id in p.path_sequence_display

    d_paths = [p for p in paths if p.target_scenario_id]
    assert {p.target_scenario_id for p in d_paths} >= {"D9", "D10"}
    for p in d_paths:
        assert p.scenario_target_label
        assert p.target_scenario_id in p.category_label
        assert p.target_scenario_id in p.path_sequence_display

    from eval1.layer1.fsm_viz_builder import build_path_fsm_projection

    probe = next(p for p in d_paths if p.target_scenario_id == "D9")
    proj = build_path_fsm_projection(
        list(probe.nodes),
        probe.node_labels,
        gb,
        target_scenario_id=probe.target_scenario_id,
        instruction=inst,
    )
    probe_node = next(n for n in proj["nodes"] if n["id"] == "PROBE_D9_BUSY")
    assert probe_node.get("scenario_id") == "D9"
    assert "D9" in probe_node["label"]


def test_paths_count_and_coverage():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    from eval1.layer1.path_coverage_builder import FAQ_ATTACH_STEPS, uncovered_branches, path_dedupe_key
    from eval1.layer1.faq_step_context import faq_interrupt_flow_step

    assert len(paths) >= 34
    assert len(paths) <= 50
    assert not uncovered_branches(gb, [p.nodes for p in paths])
    keys = [(tuple(p.nodes), p.target_knowledge_id, p.target_scenario_id) for p in paths]
    assert len(keys) == len(set(keys))
    faq_steps = {faq_interrupt_flow_step(p.nodes) for p in paths if "FAQ_NORMAL" in p.nodes}
    for step in FAQ_ATTACH_STEPS:
        assert step in faq_steps
    assert any(PROBE_D9_BUSY in p.nodes for p in paths)
    assert any(PROBE_D10_DRIVE in p.nodes for p in paths)
    assert any("FAQ_OOB" in p.nodes for p in paths)


def test_instruction1_still_has_linear_f_sequence():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[0].iloc[-1])
    inst = asyncio.run(InstructionParserAgent().parse("instruction_1", raw))
    gb = RuleGraphBuilder.build_from_instruction(inst)
    assert gb.g.has_edge("F1", "F2")
    assert not instruction_has_flow_branches(inst)
