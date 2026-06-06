from eval1.layer1.models import Constraint, ConstraintType, KnowledgeNode, ParsedInstruction
from eval1.layer1.path_descriptions import (
    build_node_label_catalog,
    describe_path_flow,
    describe_path_rules,
    enrich_path_dict,
)


def _sample_instruction() -> ParsedInstruction:
    return ParsedInstruction(
        instruction_id="t1",
        raw_text="",
        role_description="站长",
        task_description="通知飞毛腿合同",
        opening_line="你好，请问是${rider_name}吗？单日 **X 单**，多日 **Y 单**。",
        flow_steps=[
            "告知骑手今天飞毛腿合同已生效，并询问他们是否可以开始配送。",
            "说明单日飞毛腿合同需要连续 Y 天完成配送；否则合同将受到影响。",
            "尽量挽留不想配送的骑手，鼓励能配送的骑手，并提醒他们注意安全。",
            "说明飞毛腿报名是按排名进行的，并非站长干预。",
        ],
        constraints=[
            Constraint(
                id="B1",
                type=ConstraintType.BOUNDARY,
                text='如被问及超出职责范围的问题，回复："我向同事确认后再回电给你。"',
            ),
            Constraint(
                id="D9",
                type=ConstraintType.DIALOGUE,
                text="如果骑手坚持确实无法配送，安慰他们后挂断电话。",
            ),
        ],
        knowledge_nodes=[
            KnowledgeNode(id="K1", text="单日合同：在生效当天必须完成 X 单。", trigger_type="on_user_ask"),
        ],
        variables={},
    )


def test_node_catalog_uses_call_flow_text():
    inst = _sample_instruction()
    slots = {"rider_name": "张伟", "X": "5", "Y": "3"}
    catalog = build_node_label_catalog(inst, slots)
    assert "张伟" in catalog["START"]
    assert "连续 3 天" in catalog["F2"]
    assert "Call Flow 第 3 步" in catalog["F3_RETAIN"]


def test_path_flow_description_numbered():
    inst = _sample_instruction()
    nodes = ["START", "F1", "F2", "CLOSING", "END"]
    text = describe_path_flow(nodes, inst, {"X": "5", "Y": "3"})
    assert "【F1】" in text
    assert "【F2】" in text
    assert text.index("【F1】") < text.index("【F2】")


def test_enrich_path_dict_adds_fields():
    inst = _sample_instruction()
    enriched = enrich_path_dict(
        {
            "path_id": "P1",
            "nodes": ["START", "F1", "OBJ_FINAL", "END"],
            "description": "",
            "activated_rules": ["B1", "F1", "F2", "K1"],
        },
        inst,
        {"X": "5", "Y": "3"},
    )
    assert enriched["category_label"] == "挽留失败终止"
    assert "flow_description" in enriched
    assert enriched["node_labels"]["F1"].startswith("Call Flow")
    assert "rules_description" in enriched
    assert "B1" in enriched["rules_description"]
    assert enriched["rule_labels"]["B1"].startswith("边界")


def test_describe_path_rules_lists_ids():
    inst = _sample_instruction()
    text = describe_path_rules(["B1", "D9", "F1"], inst, {"X": "5", "Y": "3"})
    assert "【激活规则 · 共 3 条】" in text
    assert "· B1（" in text
    assert "· F1（" in text
