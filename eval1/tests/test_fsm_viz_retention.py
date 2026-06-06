"""FSM viz: no retention rails for instruction_2; edge trigger labels."""

import asyncio

from eval1.analysis_service import build_layer1_analysis
from eval1.data_loader import get_dataset
from eval1.layer1.fsm_viz_builder import build_goal_fsm_meta, build_path_fsm_projection
from eval1.layer1.instruction_capabilities import instruction_has_retention_rails
from eval1.layer1.path_descriptions import path_category_label
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.rule_graph import RuleGraphBuilder


def _parse_instruction_2():
    ds = get_dataset("instruction_2")
    assert ds is not None
    return asyncio.run(InstructionParserAgent().parse("instruction_2", ds["raw_instruction"]))


def test_instruction_2_has_no_retention_rails():
    parsed = _parse_instruction_2()
    assert instruction_has_retention_rails(parsed) is False
    gb = RuleGraphBuilder.build_from_instruction(parsed)
    assert "F3_RETAIN" not in gb.g
    assert "OBJ_FINAL" not in gb.g


def test_instruction_2_fsm_edges_have_trigger_labels():
    parsed = _parse_instruction_2()
    gb = RuleGraphBuilder.build_from_instruction(parsed)
    meta = build_goal_fsm_meta(gb, parsed)
    node_ids = {n["id"] for n in meta["nodes"]}
    assert "F3_RETAIN" not in node_ids
    assert meta["edges"]
    assert all(e.get("label") for e in meta["edges"])


def test_instruction_2_layer1_includes_flow_branches_by_step():
    result = asyncio.run(build_layer1_analysis("instruction_2"))
    by_step = (result.get("parsed") or {}).get("flow_branches_by_step") or {}
    assert len(by_step.get("4", [])) >= 4
    assert any("Web" in (b.get("section") or "") for b in by_step.get("4", []))


def test_instruction_1_layer1_has_empty_flow_branches():
    result = asyncio.run(build_layer1_analysis("instruction_1"))
    by_step = (result.get("parsed") or {}).get("flow_branches_by_step") or {}
    assert by_step == {}


def test_instruction_2_no_retention_paths_in_layer1():
    result = asyncio.run(build_layer1_analysis("instruction_2"))
    for path in result.get("paths") or []:
        nodes = path.get("nodes") or []
        assert "F3_RETAIN" not in nodes
        assert "OBJ_FINAL" not in nodes
        assert "挽留" not in path_category_label(nodes)
    fsm_nodes = {n["id"] for n in (result.get("goal_fsm") or {}).get("nodes") or []}
    assert "F3_RETAIN" not in fsm_nodes


def test_path_fsm_projection_labels_from_graph():
    parsed = _parse_instruction_2()
    gb = RuleGraphBuilder.build_from_instruction(parsed)
    nodes = ["START", "F1", "F2", "F3"]
    proj = build_path_fsm_projection(nodes, gb=gb)
    assert len(proj["edges"]) == 3
    assert proj["edges"][0]["label"] == "开场"
