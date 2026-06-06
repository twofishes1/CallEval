from __future__ import annotations

from typing import List, Tuple

PROBE_D9_BUSY = "PROBE_D9_BUSY"
PROBE_D10_DRIVE = "PROBE_D10_DRIVE"

_PROBE_NODES = frozenset({PROBE_D9_BUSY, PROBE_D10_DRIVE})

PROBE_CONSTRAINT_MAP: dict[str, str] = {
    PROBE_D9_BUSY: "D9",
    PROBE_D10_DRIVE: "D10",
}


def is_probe_node(node: str) -> bool:
    return str(node or "") in _PROBE_NODES


def probe_constraint_id(node: str) -> str:
    return PROBE_CONSTRAINT_MAP.get(str(node or ""), "")


def probe_constraint_for_path(path_nodes: List[str]) -> str:
    for n in path_nodes or []:
        cid = probe_constraint_id(str(n))
        if cid:
            return cid
    return ""


def scenario_path_desc_tag(desc: str) -> str:
    """Parse target D id from path desc, e.g. probe_busy_d9@D9 -> D9."""
    text = str(desc or "")
    if "@" in text:
        tag = text.rsplit("@", 1)[-1].strip()
        if tag.startswith("D"):
            return tag
    if text == "probe_busy_d9":
        return "D9"
    if text == "probe_drive_d10":
        return "D10"
    return ""


def probe_user_line(node: str) -> str:
    if node == PROBE_D9_BUSY:
        return "我现在有点忙，能简短点吗？"
    if node == PROBE_D10_DRIVE:
        return "我在开车，不太方便接电话。"
    return ""


def _canonical_mainline_branches(path: List[str]) -> List[str]:
    """Pick cooperative main branches from an existing path."""
    out: List[str] = []
    seen_steps: set[str] = set()
    for n in path:
        if not str(n).startswith("branch::"):
            continue
        parts = str(n).split("::")
        step = parts[1] if len(parts) > 1 else ""
        if step in seen_steps:
            continue
        seen_steps.add(step)
        if len(parts) >= 4 and parts[2] == "main":
            out.append(f"branch::{step}::main::1")
        else:
            out.append(str(n))
    return out


def _insert_after(path: List[str], anchor: str, insert: str) -> List[str] | None:
    nodes = list(path)
    if anchor not in nodes:
        return None
    idx = nodes.index(anchor)
    if insert in nodes:
        return None
    return nodes[: idx + 1] + [insert] + nodes[idx + 1 :]


def _insert_before(path: List[str], anchor: str, insert: str) -> List[str] | None:
    nodes = list(path)
    if anchor not in nodes or insert in nodes:
        return None
    idx = nodes.index(anchor)
    return nodes[:idx] + [insert] + nodes[idx:]


def build_faq_paths(base_path: List[str], *, attach_after: str = "F2") -> List[Tuple[List[str], str]]:
    """FAQ interrupt paths derived from a mainline template."""
    out: List[Tuple[List[str], str]] = []
    nodes = list(base_path)

    faq_normal = _insert_after(nodes, attach_after, "FAQ_NORMAL") if attach_after in nodes else None
    if faq_normal:
        out.append((faq_normal, "contains_faq_interrupt"))

    faq_oob = _insert_before(nodes, "F4", "FAQ_OOB") if "F4" in nodes else None
    if faq_oob and faq_oob != faq_normal:
        out.append((faq_oob, "contains_oob_faq"))
    return out


def build_constraint_probe_paths(base_path: List[str]) -> List[Tuple[List[str], str]]:
    """D9 busy / D10 driving probe paths after identity confirm."""
    out: List[Tuple[List[str], str]] = []
    anchor = "branch::1::main::1"
    if anchor not in base_path:
        for n in base_path:
            if str(n).startswith("branch::1::"):
                anchor = str(n)
                break
        else:
            anchor = "F1"

    busy = _insert_after(base_path, anchor, PROBE_D9_BUSY)
    if busy:
        out.append((busy, f"probe_busy_d9@{PROBE_CONSTRAINT_MAP[PROBE_D9_BUSY]}"))

    drive = _insert_after(base_path, anchor, PROBE_D10_DRIVE)
    if drive:
        idx = drive.index(PROBE_D10_DRIVE)
        drive = drive[: idx + 1] + ["CLOSING", "END"]
        out.append((drive, f"probe_drive_d10@{PROBE_CONSTRAINT_MAP[PROBE_D10_DRIVE]}"))
    return out


def pick_mainline_template(paths: List[List[str]]) -> List[str]:
    """Best cooperative mainline: fewest interrupts, prefers guided F4 ops path."""
    if not paths:
        return ["START", "F1", "CLOSING", "END"]

    def score(p: List[str]) -> tuple:
        faq = int("FAQ_NORMAL" in p or "FAQ_OOB" in p)
        probe = int(any(is_probe_node(n) for n in p))
        f4 = next((n for n in p if str(n).startswith("branch::4::")), "")
        ops = sum(1 for n in p if str(n).startswith("op::"))
        return (faq + probe, -ops, -len(p), f4)

    return min(paths, key=score)
