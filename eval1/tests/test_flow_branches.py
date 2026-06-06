import networkx as nx

from eval1.layer1.models import ConstraintType, ParsedInstruction
from eval1.layer1.flow_branch_extract import is_flow_branch_line
from eval1.layer1.rule_graph import RuleGraphBuilder, _attach_flow_branches_and_ops


def test_attach_flow_branches_from_step_blocks():
    raw = """
## Step 1: 确认身份
- 若是负责人 → 进入第2步
- 若不是 → 请其转达，然后进入第2步

## Step 2: 说明来意
"""
    g = nx.DiGraph()
    g.add_node("F1", node_type="flow_step", label="确认身份")
    g.add_node("F2", node_type="flow_step", label="说明来意")
    _attach_flow_branches_and_ops(g, raw, ["F1", "F2"])

    branch_ids = [n for n in g if str(n).startswith("branch::1::")]
    assert len(branch_ids) >= 2
    assert g.has_edge("F1", branch_ids[0])
    assert not g.has_edge("F1", "F2"), "F1 must not skip branches via direct sequence"
    goto_targets = [v for u, v, d in g.edges(data=True) if u in branch_ids and d.get("edge_type") == "goto"]
    assert "F2" in goto_targets


def test_rule_graph_build_includes_branches():
    inst = ParsedInstruction(
        instruction_id="instruction_2",
        raw_text="""
## Step 1: 确认身份
- 若是负责人 → 进入第2步
- 若不是 → 请其转达，然后进入第2步
## Step 2: 说明来意
""",
        role_description="客服",
        task_description="外呼",
        opening_line="您好",
        flow_steps=["确认身份", "说明来意"],
        constraints=[],
        knowledge_nodes=[],
        variables={},
    )
    gb = RuleGraphBuilder.build_from_instruction(inst)
    branch_ids = [n for n, d in gb.g.nodes(data=True) if d.get("node_type") == "flow_branch"]
    assert len(branch_ids) == 2
    assert gb.g.has_edge("F1", branch_ids[0])
