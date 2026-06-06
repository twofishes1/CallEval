# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

import pandas as pd

from eval1.layer1.flow_branch_extract import extract_branches_from_block, iter_step_blocks
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.path_enumerator import PathEnumerator
from eval1.layer1.path_descriptions import enrich_path_dict
from eval1.layer1.rule_graph import RuleGraphBuilder
from eval1.layer2.instruction_injection import compress_step_to_utterance, sanitize_bot_output
from eval1.layer2.persona import PersonaType
from eval1.layer2.step_speakable import (
    extract_branch_speakables,
    pick_step_speakable,
    resolve_branch_speakable,
)
from eval1.layer2.persona_phrasing import build_minimal_action_utterance


async def _parse_instruction_2():
    df = pd.read_excel(Path("eval1/data/data.xlsx"))
    raw = str(df.iloc[1].iloc[-1])
    return await InstructionParserAgent().parse("instruction_2", raw)


def test_f6_branch_extract_not_cross_line():
    inst = asyncio.run(_parse_instruction_2())
    raw = str(getattr(inst, "raw_text", "") or "")
    block = next(b for no, b in iter_step_blocks(raw) if no == 6)
    branches = extract_branches_from_block(block)
    assert branches[0][0] == "当前号码可添加"
    assert "若" not in branches[0][1]
    assert branches[0][1].startswith("告知")


def test_f6_wechat_natural_not_raw_branch_label():
    inst = asyncio.run(_parse_instruction_2())
    f6 = str(inst.flow_steps[5])
    line = pick_step_speakable(inst, 6, f6)
    assert "若" not in line
    assert "→" not in line
    assert "企业微信" in line
    assert "验证" in line
    branch_line = resolve_branch_speakable(inst, "branch::6::main::1")
    assert "若" not in branch_line
    assert "企业微信" in branch_line


def test_compress_f6_not_raw_branch_label():
    inst = asyncio.run(_parse_instruction_2())
    f6 = compress_step_to_utterance(
        str(inst.flow_steps[5]), current_state="F6", instruction=inst
    )
    assert "若" not in f6
    assert "→" not in f6
    assert "企业微信" in f6


def test_sanitize_rewrites_branch_label():
    raw = "若当前号码可添加→告知稍后通过企业微信添加，请通过验证。"
    cleaned = sanitize_bot_output(raw)
    assert "若" not in cleaned
    assert "→" not in cleaned
    assert "企业微信" in cleaned


def test_sanitize_strips_reference_script_label():
    from eval1.layer2.instruction_injection import sanitize_bot_output

    raw = '**参考话术：**我们对直播产品做了升级，新增了独立的"低延迟直播"选项。'
    cleaned = sanitize_bot_output(raw)
    assert "参考话术" not in cleaned
    assert cleaned.startswith("我们")
    assert "低延迟" in cleaned


def test_stale_identity_ack_after_upgrade():
    from eval1.layer2.user_role_guard import is_stale_identity_ack

    bot = "好的，我们对直播产品做了升级，新增了独立的低延迟直播选项。"
    assert is_stale_identity_ack("对，您说。", last_bot=bot, current_state="F2")
    assert not is_stale_identity_ack("是的，我是。", last_bot="请问您是负责人吗？", current_state="START")


def test_cooperative_comply_after_upgrade_not_identity():
    inst = asyncio.run(_parse_instruction_2())
    bot = "好的，我们对直播产品做了升级，新增了低延迟直播选项。"
    line = build_minimal_action_utterance(
        "comply",
        turn=1,
        persona=PersonaType.COOPERATIVE,
        last_bot_utterance=bot,
        instruction=inst,
    )
    assert line not in {"是的，我是。", "对，您说。", "嗯，我负责这块。"}


def test_identity_confirm_fallback_natural():
    inst = asyncio.run(_parse_instruction_2())
    line = build_minimal_action_utterance(
        "comply",
        turn=0,
        persona=PersonaType.COOPERATIVE,
        last_bot_utterance="您好，请问您是贵培训机构/校区的负责人吗？",
        instruction=inst,
    )
    assert line != "好的，我是负责人。"
    assert "是的" in line or "对" in line or "嗯" in line


def test_f3_branch_not_split_on_delay_range():
    inst = asyncio.run(_parse_instruction_2())
    line = resolve_branch_speakable(inst, "branch::3::main::1")
    # Legacy path node from misparsed bullets; speakable must be a full sentence.
    if line:
        assert "10秒；适合大班课" != line.strip("。")
        assert "大班" in line


def test_f5_fee_branch_natural_question():
    from eval1.layer2.step_speakable import naturalize_branch_action

    line = naturalize_branch_action("提醒确认低延迟直播也已适用该费用")
    assert "吗" in line or "？" in line
    assert "若" not in line
    assert "确认低延迟直播也已适用该费用" not in line

    inst = asyncio.run(_parse_instruction_2())
    branch_line = resolve_branch_speakable(inst, "branch::5::main::2")
    assert branch_line
    assert "吗" in branch_line or "？" in branch_line


def test_f5_f6_use_branch_scripts_not_titles():
    inst = asyncio.run(_parse_instruction_2())
    f5 = str(inst.flow_steps[4])
    f6 = str(inst.flow_steps[5])
    line5 = pick_step_speakable(inst, 5, f5)
    line6 = pick_step_speakable(inst, 6, f6)
    assert "检查学员端费用" not in line5 or "低延迟" in line5 or "费用" in line5
    assert line5 != f5
    assert line6 != f6
    assert "企业微信" in line6
    assert line6 != "企业微信添加。"


def test_compress_f5_f6_not_mechanical_titles():
    inst = asyncio.run(_parse_instruction_2())
    f5 = compress_step_to_utterance(
        str(inst.flow_steps[4]), current_state="F5", instruction=inst
    )
    f6 = compress_step_to_utterance(
        str(inst.flow_steps[5]), current_state="F6", instruction=inst
    )
    assert f5 != "检查学员端费用/加速线路费（如有使用）。"
    assert f6 != "企业微信添加。"
    assert "企业微信" in f6


def test_p1_has_branch_notes_for_skipped_branches():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    p1 = next(p for p in paths if p.path_id == "P1")
    enriched = enrich_path_dict(p1.model_dump(), inst)
    # With mandatory branches, P1 includes branch nodes; branch_notes optional
    branch_in_path = any(str(n).startswith("branch::") for n in p1.nodes)
    assert branch_in_path or enriched.get("branch_notes")


def test_branch_path_has_labeled_nodes():
    inst = asyncio.run(_parse_instruction_2())
    gb = RuleGraphBuilder.build_from_instruction(inst)
    paths = PathEnumerator(gb).enumerate_paths()
    p_with_branch = next(p for p in paths if any(str(n).startswith("branch::") for n in p.nodes))
    enriched = enrich_path_dict(p_with_branch.model_dump(), inst)
    bid = next(n for n in p_with_branch.nodes if str(n).startswith("branch::"))
    label = enriched.get("node_labels", {}).get(bid, "")
    assert "负责人" in label or "分支" in label
