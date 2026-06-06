from __future__ import annotations

import re
from typing import List, Tuple

# Conditional branch: "若… → …" or "条件 → …"
_RANGE_ARROW_RE = re.compile(r"(\d+)\s*→\s*(\d+)\s*秒")
_RANGE_HYPHEN_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*秒")


def _normalize_range_arrows(text: str) -> str:
    """Delay ranges like 5-10秒 / 5 → 10秒 are not branch arrows."""
    t = _RANGE_ARROW_RE.sub(r"\1到\2秒", text or "")
    return _RANGE_HYPHEN_RE.sub(r"\1到\2秒", t)


BRANCH_LINE_RE = re.compile(
    r"^\s*[-*•]?\s*(?:\*\*)?(?:若\s*)?(.+?)\s*→\s*(.+?)\s*(?:\*\*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
STEP_HEADER_RE = re.compile(r"(?mi)^##\s*Step\s*(\d+)\s*[:：]\s*(.+?)\s*$")


def is_flow_branch_line(line: str) -> bool:
    return bool(BRANCH_LINE_RE.match(str(line or "").strip()))


def parse_branch_line(line: str) -> Tuple[str, str] | None:
    m = BRANCH_LINE_RE.match(_normalize_range_arrows(str(line or "").strip()))
    if not m:
        return None
    cond = (m.group(1) or "").strip()
    act = (m.group(2) or "").strip()
    if not cond or not act:
        return None
    return cond, act


def extract_branches_from_block(block: str) -> List[Tuple[str, str]]:
    """Parse branch (condition, action) pairs from one ## Step block."""
    if not block:
        return []
    hdr = STEP_HEADER_RE.search(block)
    step_no = int(hdr.group(1)) if hdr else 0
    if step_no < 1:
        out: List[Tuple[str, str]] = []
        seen: set[Tuple[str, str]] = set()
        for line in (block or "").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parsed = parse_branch_line(s)
            if parsed and parsed not in seen:
                seen.add(parsed)
                out.append(parsed)
        return out
    from eval1.layer1.flow_branch_model import parse_step_branches

    return [(b.condition, b.action) for b in parse_step_branches(block, step_no)]


def iter_step_blocks(raw: str) -> List[Tuple[int, str]]:
    if not raw:
        return []
    starts = [(m.start(), int(m.group(1)), (m.group(2) or "").strip()) for m in STEP_HEADER_RE.finditer(raw)]
    if not starts:
        return []
    starts.append((len(raw), -1, ""))
    blocks: List[Tuple[int, str]] = []
    for idx in range(len(starts) - 1):
        start_pos, step_no, _ = starts[idx]
        end_pos, _, _ = starts[idx + 1]
        if step_no > 0:
            blocks.append((step_no, raw[start_pos:end_pos]))
    return blocks
