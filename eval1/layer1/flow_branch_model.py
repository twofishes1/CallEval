# -*- coding: utf-8 -*-
"""Structured branch model for instruction_2-style Call Flow steps."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from eval1.layer1.flow_branch_extract import _normalize_range_arrows, iter_step_blocks

# 若…→…  or  条件→…  (F5: 未设置费用 → 进入第6步)
_BRANCH_LINE_RE = re.compile(
    r"^\s*[-*•]?\s*(?:\*\*)?(?:若\s*)?(.+?)\s*→\s*(.+?)\s*(?:\*\*)?\s*$",
    re.MULTILINE,
)
_SECTION_RE = re.compile(r"^\s*\*\*(.+?)[:：]\*\*\s*$", re.MULTILINE)
_OP_LINE_RE = re.compile(r"^\s*\d+\.\s*(.+?)\s*$", re.MULTILINE)
_GOTO_STEP_RE = re.compile(r"进入第\s*(\d+)\s*步")
_GUIDE_MARKER_RE = re.compile(r"每步暂停\s*3\s*秒|缓慢引导")


@dataclass(frozen=True)
class StructuredBranch:
    step_no: int
    branch_index: int
    condition: str
    action: str
    section: str = ""
    target_step: Optional[int] = None
    op_steps: Tuple[str, ...] = field(default_factory=tuple)
    branch_id: str = ""

    def __post_init__(self) -> None:
        if not self.branch_id:
            sec = _slug(self.section) if self.section else "main"
            object.__setattr__(
                self,
                "branch_id",
                f"branch::{self.step_no}::{sec}::{self.branch_index}",
            )


def _slug(text: str) -> str:
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (text or "").strip())[:16].strip("_")
    return t or "main"


def _parse_target_step(action: str) -> Optional[int]:
    m = _GOTO_STEP_RE.search(action or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _collect_ops_after(lines: List[str], start_idx: int) -> Tuple[str, ...]:
    ops: List[str] = []
    for line in lines[start_idx:]:
        s = line.strip()
        if not s:
            continue
        if _BRANCH_LINE_RE.match(s) or _SECTION_RE.match(s):
            break
        if s.startswith("##"):
            break
        m = _OP_LINE_RE.match(s)
        if m:
            ops.append(m.group(1).strip())
        elif ops:
            break
    return tuple(ops)


def parse_step_branches(block: str, step_no: int) -> List[StructuredBranch]:
    """Parse one ## Step block into structured branches with section + op chains."""
    if not block:
        return []

    lines = block.splitlines()
    section = ""
    out: List[StructuredBranch] = []
    branch_counter = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        sec_m = _SECTION_RE.match(stripped)
        if sec_m:
            section = sec_m.group(1).strip()
            i += 1
            continue

        br_m = _BRANCH_LINE_RE.match(_normalize_range_arrows(stripped))
        if br_m:
            cond = (br_m.group(1) or "").strip().strip("*")
            act = (br_m.group(2) or "").strip().strip("*")
            if not cond or not act:
                i += 1
                continue
            # skip reference script / ask lines mis-parsed as branches
            if cond.startswith(("参考话术", "询问")) or act.startswith(("参考话术", "询问")):
                i += 1
                continue
            if len(cond) > 80 and "。" in cond:
                i += 1
                continue

            branch_counter += 1
            ops: Tuple[str, ...] = ()
            if _GUIDE_MARKER_RE.search(act):
                ops = _collect_ops_after(lines, i + 1)

            out.append(
                StructuredBranch(
                    step_no=step_no,
                    branch_index=branch_counter,
                    condition=cond,
                    action=act,
                    section=section,
                    target_step=_parse_target_step(act),
                    op_steps=ops,
                )
            )
        i += 1

    return out


def parse_instruction_branches(raw: str) -> List[StructuredBranch]:
    branches: List[StructuredBranch] = []
    for step_no, block in iter_step_blocks(raw):
        branches.extend(parse_step_branches(block, step_no))
    return branches


def branches_by_step(raw: str) -> dict[int, List[StructuredBranch]]:
    out: dict[int, List[StructuredBranch]] = {}
    for b in parse_instruction_branches(raw):
        out.setdefault(b.step_no, []).append(b)
    return out


def instruction_has_structured_branches(instruction) -> bool:
    raw = str(getattr(instruction, "raw_text", "") or "")
    return bool(parse_instruction_branches(raw))


def branch_to_dict(branch: StructuredBranch) -> dict:
    return {
        "branch_id": branch.branch_id,
        "step_no": branch.step_no,
        "branch_index": branch.branch_index,
        "condition": branch.condition,
        "action": branch.action,
        "section": branch.section,
        "target_step": branch.target_step,
        "op_steps": list(branch.op_steps),
    }


def flow_branches_by_step_for_instruction(instruction) -> dict[str, list[dict]]:
    """UI-friendly branch map keyed by step number string ('1'..'7')."""
    raw = str(getattr(instruction, "raw_text", "") or "")
    by_step = branches_by_step(raw)
    return {
        str(step): [branch_to_dict(b) for b in branches]
        for step, branches in sorted(by_step.items())
    }
