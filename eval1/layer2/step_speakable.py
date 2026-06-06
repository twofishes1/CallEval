# -*- coding: utf-8 -*-
"""Map Call Flow F-steps to speakable lines (参考话术 / 询问 / 分支动作)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from eval1.layer1.flow_branch_extract import extract_branches_from_block, iter_step_blocks
from eval1.layer2.instruction_injection import substitute_variables, _char_len

_SCRIPT_LINE_RE = re.compile(
    r"(?:参考话术|询问)\s*[：:]\s*(.+?)(?:\*\*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_GOTO_ONLY_RE = re.compile(r"^\s*进入第\s*\d+\s*步\s*$")
_OP_LINE_RE = re.compile(r"(?m)^\s*\d+\.\s*(.+?)\s*$")


def _step_block(raw: str, step_no: int) -> str:
    for no, block in iter_step_blocks(raw):
        if no == step_no:
            return block
    return ""


def extract_step_scripts(raw: str, step_no: int) -> List[str]:
    block = _step_block(raw, step_no)
    out: List[str] = []
    seen: set[str] = set()
    for m in _SCRIPT_LINE_RE.finditer(block):
        t = re.sub(r"\*+", "", m.group(1)).strip().strip("。")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def extract_branch_speakables(raw: str, step_no: int) -> List[str]:
    block = _step_block(raw, step_no)
    out: List[str] = []
    for _cond, act in extract_branches_from_block(block):
        a = re.sub(r"\*+", "", act).strip()
        if not a or _GOTO_ONLY_RE.match(a):
            continue
        if a not in out:
            out.append(a)
    return out


def extract_op_speakables(raw: str, step_no: int) -> List[str]:
    block = _step_block(raw, step_no)
    if not re.search(r"每步暂停\s*3\s*秒", block):
        return []
    out: List[str] = []
    for m in _OP_LINE_RE.finditer(block):
        t = re.sub(r"\*+", "", m.group(1)).strip()
        if t and t not in out:
            out.append(t)
    return out


def build_step_script_map(instruction: Any) -> Dict[int, List[str]]:
    raw = str(getattr(instruction, "raw_text", "") or "")
    if not raw:
        return {}
    out: Dict[int, List[str]] = {}
    for step_no, _block in iter_step_blocks(raw):
        lines = extract_step_scripts(raw, step_no)
        lines.extend(x for x in extract_branch_speakables(raw, step_no) if x not in lines)
        if lines:
            out[step_no] = lines
    return out


def build_branch_label_catalog(instruction: Any) -> Dict[str, str]:
    raw = str(getattr(instruction, "raw_text", "") or "")
    catalog: Dict[str, str] = {}
    for step_no, block in iter_step_blocks(raw):
        for i, (cond, act) in enumerate(extract_branches_from_block(block), start=1):
            bid = f"branch::{step_no}::{i}"
            catalog[bid] = f"分支·F{step_no}：若{cond} → {act}"
    return catalog


def list_step_branches(instruction: Any, step_no: int) -> List[Tuple[str, str]]:
    raw = str(getattr(instruction, "raw_text", "") or "")
    return extract_branches_from_block(_step_block(raw, step_no))


_BRANCH_LABEL_RE = re.compile(
    r"^(?:若|如果).+?[→\-]{1,2}\s*(.+?)\s*$",
    re.IGNORECASE,
)


def _naturalize_live_product_line(action: str, *, max_len: int = 30) -> str:
    """Turn F3 标准/低延迟 feature bullets into one phone sentence."""
    act = re.sub(r"\*+", "", (action or "")).strip()
    if "低延迟" in act and "费用" in act and "适用" in act:
        return ""
    if "标准直播" in act or ("费用" in act and "大班" in act and "低延迟" not in act):
        return _shorten_for_phone(
            "标准直播费用低些，延迟大概五到十秒，适合大班课。",
            max_len,
        )
    if "低延迟" in act or "小班" in act or "实操" in act:
        return _shorten_for_phone(
            "低延迟一两秒，互动更顺，适合小班和实操课。",
            max_len,
        )
    if "；" in act and any(k in act for k in ("秒", "费用", "适合", "延迟")):
        parts = [p.strip() for p in act.split("；") if p.strip()]
        if len(parts) >= 2:
            body = "，".join(parts[:3])
            return _shorten_for_phone(f"{body}。", max_len)
    return ""


def naturalize_branch_action(action: str, *, max_len: int = 30) -> str:
    """Turn branch action/meta instruction into a natural phone utterance."""
    act = re.sub(r"\*+", "", (action or "").strip()).strip()
    if not act:
        return ""
    product_line = _naturalize_live_product_line(act, max_len=max_len)
    if product_line:
        return product_line
    if _GOTO_ONLY_RE.match(act):
        return "好的，我们继续下一步。"
    m = _BRANCH_LABEL_RE.match(act)
    if m:
        act = m.group(1).strip()
    if re.search(r"[→\-]{1,2}", act) and "若" in act:
        act = re.split(r"[→\-]{1,2}", act)[-1].strip()
    act = re.sub(r"^(告知|提醒|说明)(稍后)?", "", act).strip()
    act = re.sub(r"^请(稍后)?", "", act).strip()
    if "企业微信" in act and "验证" in act:
        return _shorten_for_phone("稍后会加您企业微信，麻烦通过验证。", max_len)
    if "企业微信" in act and "手机号" in act:
        return _shorten_for_phone("请留一个能加企业微信的手机号。", max_len)
    if act in {"直接使用", "按需选择即可"}:
        return _shorten_for_phone("好的，前端已显示，可以直接使用。", max_len)
    if act.startswith("后台为其配置"):
        return _shorten_for_phone("后台给您配好，明天再看一下就行。", max_len)
    if act.startswith("进入第") and "步" in act:
        return "好的，我们继续。"
    if act.startswith("缓慢引导"):
        return _shorten_for_phone("我带您一步步设置。", max_len)
    if act.startswith("确认") and "吗" not in act and "?" not in act:
        if "低延迟" in act and "费用" in act:
            return _shorten_for_phone("学员端费用设好了吗？低延迟也走同一套。", max_len)
        if "费用" in act:
            return _shorten_for_phone(f"{act.replace('确认', '帮您确认一下，')}可以吗？", max_len)
        return _shorten_for_phone(f"{act}，您这边方便吗？", max_len)
    if act.startswith("确认") or act.startswith("检查"):
        return _shorten_for_phone(f"想跟您确认一下，{act.lstrip('确认检查')}，可以吗？", max_len)
    return _shorten_for_phone(act, max_len)


def _shorten_for_phone(text: str, max_len: int = 30) -> str:
    t = re.sub(r"\s+", "", (text or "").strip())
    t = re.sub(r"^(告知|提醒|说明|请)", "", t).strip()
    if _char_len(t) <= max_len:
        return t if t.endswith(("。", "！", "？", "?", "！")) else f"{t}。"
    return t[: max_len - 1] + "。"


def _step_title_needs_script(step_text: str) -> bool:
    t = (step_text or "").strip()
    if not t or len(t) < 4:
        return True
    if "？" in t or "?" in t or t.endswith(("吗", "呢")):
        return False
    if len(t) <= 24 and any(k in t for k in ("检查", "添加", "确认", "开通", "引导", "/")):
        return True
    if "（" in t and "）" in t and len(t) <= 28:
        return True
    return False


def pick_step_speakable(
    instruction: Any,
    step_index: int,
    step_text: str = "",
    slots: Dict[str, str] | None = None,
    *,
    max_len: int = 30,
) -> str:
    """Best phone utterance for F{step_index} from instruction raw blocks."""
    if instruction is None or step_index < 1:
        return ""
    slots = dict(slots or {})
    raw = str(getattr(instruction, "raw_text", "") or "")

    scripts = extract_step_scripts(raw, step_index)
    for s in scripts:
        if "？" in s or "?" in s or "吗" in s:
            return _shorten_for_phone(substitute_variables(s, slots), max_len)

    title = substitute_variables(step_text or "", slots)
    if step_index == 4 and title and _step_title_needs_script(title) and scripts:
        return _shorten_for_phone(substitute_variables(scripts[0], slots), max_len)

    branches = extract_branch_speakables(raw, step_index)
    if branches:
        return naturalize_branch_action(substitute_variables(branches[0], slots), max_len=max_len)

    if scripts:
        return _shorten_for_phone(substitute_variables(scripts[0], slots), max_len)

    ops = extract_op_speakables(raw, step_index)
    if ops:
        return _shorten_for_phone(substitute_variables(ops[0], slots), max_len)

    title = substitute_variables(step_text or "", slots)
    if title and not _step_title_needs_script(title):
        return _shorten_for_phone(title, max_len)
    return ""


def resolve_branch_speakable(
    instruction: Any,
    branch_id: str,
    slots: Dict[str, str] | None = None,
    *,
    max_len: int = 30,
) -> str:
    """Speakable line when FSM is on a branch node."""
    if instruction is None:
        return ""
    from eval1.layer1.flow_branch_model import parse_instruction_branches

    for br in parse_instruction_branches(str(getattr(instruction, "raw_text", "") or "")):
        if br.branch_id == branch_id:
            action = substitute_variables(br.action.strip(), slots)
            spoken = naturalize_branch_action(action, max_len=max_len)
            if spoken:
                return spoken
            combined = f"{br.condition} {br.action}"
            product = _naturalize_live_product_line(combined, max_len=max_len)
            if product:
                return product
            return spoken
    # branch::step::section::index or legacy branch::step::index
    m = re.match(r"branch::(\d+)::(?:.+::)?(\d+)$", str(branch_id or ""))
    if m:
        from eval1.layer1.flow_branch_extract import extract_branches_from_block, iter_step_blocks

        step_no = int(m.group(1))
        branch_i = int(m.group(2))
        raw = str(getattr(instruction, "raw_text", "") or "")
        for no, block in iter_step_blocks(raw):
            if no == step_no:
                branches = extract_branches_from_block(block)
                if 1 <= branch_i <= len(branches):
                    _cond, act = branches[branch_i - 1]
                    return naturalize_branch_action(
                        substitute_variables(act.strip(), slots), max_len=max_len
                    )
    # Legacy path nodes: F3 product bullets were once misparsed as branches.
    m3 = re.match(r"branch::3::(?:.+::)?(\d+)$", str(branch_id or ""))
    if m3 and instruction:
        idx = int(m3.group(1))
        if idx == 1:
            return _naturalize_live_product_line("标准直播 费用较低 适合大班课", max_len=max_len)
        if idx == 2:
            return _naturalize_live_product_line("低延迟直播 互动更流畅 小班课", max_len=max_len)
        line = pick_step_speakable(instruction, 3, slots=slots, max_len=max_len)
        if line:
            return line
    return ""


def resolve_op_speakable(
    instruction: Any,
    op_id: str,
    slots: Dict[str, str] | None = None,
    *,
    max_len: int = 48,
) -> str:
    """Speakable line when FSM is on an op:: guided-setup node (instruction_2 F4 等)."""
    if instruction is None:
        return ""
    m = re.match(r"op::(\d+)::(\d+)::(\d+)$", str(op_id or ""))
    if not m:
        return ""
    step_no = int(m.group(1))
    branch_index = int(m.group(2))
    op_index = int(m.group(3))
    from eval1.layer1.flow_branch_model import parse_instruction_branches

    for br in parse_instruction_branches(str(getattr(instruction, "raw_text", "") or "")):
        if br.step_no == step_no and br.branch_index == branch_index:
            ops = list(br.op_steps or ())
            if 1 <= op_index <= len(ops):
                text = substitute_variables(str(ops[op_index - 1]).strip(), slots)
                spoken = naturalize_branch_action(text, max_len=max_len)
                return spoken or _shorten_for_phone(text, max_len)
    return f"请按第{op_index}步操作说明继续配置"


def describe_skipped_branches(path_nodes: List[str], instruction: Any) -> str:
    """Branches on F-steps that this path does not explicitly visit."""
    if not instruction:
        return ""
    present = {str(n) for n in (path_nodes or [])}
    lines: List[str] = []
    raw = str(getattr(instruction, "raw_text", "") or "")
    for step_no, block in iter_step_blocks(raw):
        fnode = f"F{step_no}"
        if fnode not in present:
            continue
        branches = extract_branches_from_block(block)
        if not branches:
            continue
        taken = [f"branch::{step_no}::{i}" for i in range(1, len(branches) + 1) if f"branch::{step_no}::{i}" in present]
        if taken:
            continue
        for i, (cond, act) in enumerate(branches, start=1):
            lines.append(f"· F{step_no} 可选分支：若{cond} → {act}")
    if not lines:
        return ""
    return "本路径为顺流程主干，下列分支在对话中按用户回应动态触发（未单独枚举为路径节点）：\n" + "\n".join(lines[:12])
