import asyncio

from eval1.layer1.preprocessor import InstructionPreprocessor
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.path_enumerator import PathEnumerator
from eval1.layer1.rule_graph import RuleGraphBuilder


def test_preprocessor_smoke():
    raw = """
## Role
你是客服
## Task
挽留用户
## Call Flow
1. 先确认问题
2. 给出方案
"""
    out = InstructionPreprocessor().preprocess(raw)
    assert "sections" in out
    assert len(out["sections"]["call_flow"]) == 2


def test_parser_graph_path_smoke():
    raw = """
## Role
你是客服
## Task
挽留用户
## Call Flow
1. 先确认问题
2. 给出方案
## Knowledge
- 配送范围说明
## Constraints
- 每轮不超过30字
- 不能承诺平台不支持的能力
"""
    parsed = asyncio.run(InstructionParserAgent().parse("instruction_1", raw))
    gb = RuleGraphBuilder.build_from_instruction(parsed)
    paths = PathEnumerator(gb).enumerate_paths()
    assert parsed.instruction_id == "instruction_1"
    assert len(gb.g.nodes) > 0
    assert len(paths) > 0
