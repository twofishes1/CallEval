from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from eval1.layer1.faq_step_context import faq_interrupt_flow_step, faq_path_desc_tag, infer_faq_step_knowledge
from eval1.layer1.path_probe import (
    build_constraint_probe_paths,
    is_probe_node,
    scenario_path_desc_tag,
)
from eval1.layer1.path_plan_config import PathPlanConfig, infer_path_plan_config
from eval1.layer1.rule_graph import RuleGraphBuilder

_SKIP_SUCCESSORS = frozenset(
    {
        "GLOBAL_DIALOGUE",
        "GLOBAL_BOUNDARY",
        "FAQ_NORMAL",
        "FAQ_OOB",
        "OBJECTION",
        "F3_RETAIN",
        "OBJ_FINAL",
    }
)

# Back-compat alias: FAQ attach steps for branched tasks (prefer infer_path_plan_config).
FAQ_ATTACH_STEPS = ("F2", "F3", "F4", "F5", "F7")


def _step_no(node: str) -> Optional[int]:
    if node.startswith("F") and node[1:].isdigit():
        return int(node[1:])
    if str(node).startswith("branch::"):
        parts = str(node).split("::")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    if str(node).startswith("op::"):
        parts = str(node).split("::")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    return None


def _branch_nodes(g: nx.DiGraph) -> List[str]:
    return sorted(n for n in g.nodes if str(n).startswith("branch::"))


def _branches_by_step(g: nx.DiGraph) -> Dict[int, List[str]]:
    out: Dict[int, List[str]] = defaultdict(list)
    for bid in _branch_nodes(g):
        step = g.nodes[bid].get("step")
        if step is None:
            step = _step_no(bid)
        if step is not None:
            out[int(step)].append(bid)
    for step in out:
        out[step].sort()
    return dict(out)


def _default_branch_choices(by_step: Dict[int, List[str]]) -> Dict[int, str]:
    """Cooperative mainline defaults; F4 prefers guided third-party setup."""
    choices: Dict[int, str] = {}
    for step, bids in by_step.items():
        pick = bids[0]
        for b in bids:
            if "::main::1" in b:
                pick = b
                break
        if step == 4:
            for b in bids:
                if "第三方系统::4" in b:
                    pick = b
                    break
        choices[step] = pick
    return choices


def _follow_from(g: nx.DiGraph, node: str, *, stop_at: Optional[Set[str]] = None) -> List[str]:
    """Follow op chain or single goto from branch/op node; returns nodes after `node` (excl.)."""
    out: List[str] = []
    cur = node
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        succ = [s for s in g.successors(cur) if s not in _SKIP_SUCCESSORS]
        if not succ:
            break
        op_succ = [s for s in succ if str(s).startswith("op::")]
        if op_succ:
            cur = op_succ[0]
            out.append(cur)
            continue
        flow_succ = [s for s in succ if s.startswith("F") or s == "CLOSING"]
        if flow_succ:
            out.append(flow_succ[0])
            break
        # branch::5 guidance sub-branches
        branch_succ = [s for s in succ if str(s).startswith("branch::")]
        if branch_succ:
            cur = branch_succ[0]
            out.append(cur)
            continue
        break
    if stop_at:
        trimmed: List[str] = []
        for n in out:
            trimmed.append(n)
            if n in stop_at:
                break
        return trimmed
    return out


def walk_path(g: nx.DiGraph, flow_nodes: List[str], branch_choices: Dict[int, str]) -> Optional[List[str]]:
    """Walk START→END following forced branch picks per step."""
    path: List[str] = ["START"]
    cur = "START"
    flow_set = set(flow_nodes)

    for _ in range(max(64, len(flow_nodes) * 8)):
        if cur == "END":
            return path
        if cur == "CLOSING":
            path.append("END")
            return path

        succ = [s for s in g.successors(cur) if s not in _SKIP_SUCCESSORS]

        if cur.startswith("F") and cur[1:].isdigit():
            step = int(cur[1:])
            branch_succ = [s for s in succ if str(s).startswith("branch::")]
            if branch_succ:
                pick = branch_choices.get(step)
                if pick not in branch_succ:
                    pick = branch_succ[0]
                path.append(pick)
                rest = _follow_from(g, pick)
                path.extend(rest)
                cur = path[-1]
                continue
            if "CLOSING" in succ:
                path.append("CLOSING")
                cur = "CLOSING"
                continue

        if str(cur).startswith("branch::") or str(cur).startswith("op::"):
            rest = _follow_from(g, cur)
            if rest:
                path.extend(rest)
                cur = path[-1]
                continue

        if cur == "START":
            f1 = "F1" if "F1" in succ else next((s for s in succ if s.startswith("F")), None)
            if not f1:
                return None
            path.append(f1)
            cur = f1
            continue

        if not succ:
            return None
        nxt = succ[0]
        path.append(nxt)
        cur = nxt

    return None


def _insert_after(path: List[str], anchor: str, insert: str) -> Optional[List[str]]:
    if anchor not in path or insert in path:
        return None
    idx = path.index(anchor)
    return path[: idx + 1] + [insert] + path[idx + 1 :]


def _insert_before(path: List[str], anchor: str, insert: str) -> Optional[List[str]]:
    if anchor not in path or insert in path:
        return None
    idx = path.index(anchor)
    return path[:idx] + [insert] + path[idx:]


def _f4_branch_ids(by_step: Dict[int, List[str]]) -> List[str]:
    return list(by_step.get(4, []))


def _f6_branch_ids(by_step: Dict[int, List[str]]) -> List[str]:
    return list(by_step.get(6, []))


def _alternative_branch_ids(by_step: Dict[int, List[str]]) -> Dict[int, str]:
    """Non-default branches at identity / knowledge / pricing steps."""
    out: Dict[int, str] = {}
    for step in (1, 2, 3, 5):
        for bid in by_step.get(step, []):
            if "::main::2" in bid:
                out[step] = bid
                break
    return out


def _faq_anchor(path: List[str], step: str) -> str:
    step_no = int(step[1:])
    anchor = step
    for n in reversed(path):
        if str(n).startswith(f"branch::{step_no}::") or str(n).startswith(f"op::{step_no}::"):
            anchor = str(n)
            break
    return anchor


def build_faq_coverage_paths(
    base: List[str],
    *,
    faq_attach_steps: tuple[str, ...],
    instruction: object | None = None,
) -> List[Tuple[List[str], str]]:
    """One FAQ path per knowledge node (K*) when instruction provides knowledge mapping."""
    out: List[Tuple[List[str], str]] = []
    km = infer_faq_step_knowledge(instruction, faq_attach_steps) if instruction else {}
    seen_k: set[str] = set()
    for step in faq_attach_steps:
        if step not in base:
            continue
        anchor = _faq_anchor(base, step)
        kids = km.get(step) or ()
        if kids:
            for kid in kids:
                if kid in seen_k:
                    continue
                faq = _insert_after(base, anchor, "FAQ_NORMAL")
                if faq:
                    seen_k.add(kid)
                    out.append((faq, f"faq_after_{step.lower()}@{kid}"))
        else:
            faq = _insert_after(base, anchor, "FAQ_NORMAL")
            if faq:
                out.append((faq, f"faq_after_{step.lower()}"))
    return out


def branch_signature(path: List[str]) -> frozenset[str]:
    return frozenset(n for n in path if str(n).startswith("branch::") or str(n).startswith("op::"))


def path_dedupe_key(path: List[str], desc: str = "") -> str:
    flags: List[str] = []
    if "FAQ_NORMAL" in path:
        step = faq_interrupt_flow_step(path)
        anchor = step or (path[idx - 1] if (idx := path.index("FAQ_NORMAL")) > 0 else "START")
        kid = faq_path_desc_tag(desc)
        if kid:
            flags.append(f"FAQ@{anchor}@{kid}")
        else:
            flags.append(f"FAQ@{anchor}")
    if "FAQ_OOB" in path:
        flags.append("OOB")
    for n in path:
        if is_probe_node(n):
            flags.append(str(n))
            did = scenario_path_desc_tag(desc)
            if did:
                flags.append(f"SCN@{did}")
    branches = sorted(branch_signature(path))
    return "|".join(flags + branches)


def _try_add(
    paths: List[Tuple[List[str], str]],
    seen: Set[str],
    candidate: Optional[List[str]],
    desc: str = "structured_coverage",
) -> None:
    if not candidate:
        return
    key = path_dedupe_key(candidate, desc)
    if key in seen:
        return
    seen.add(key)
    paths.append((candidate, desc))


def build_oob_coverage_paths(base: List[str], *, oob_attach_steps: tuple[str, ...]) -> List[List[str]]:
    out: List[List[str]] = []
    for step in oob_attach_steps:
        if step not in base:
            continue
        oob = _insert_before(base, step, "FAQ_OOB")
        if oob:
            out.append(oob)
    return out


def build_minimal_coverage_paths(
    gb: RuleGraphBuilder,
    config: PathPlanConfig | None = None,
) -> List[Tuple[List[str], str]]:
    """
    Structured coverage (shared by branched and linear tasks):
    - branch grid when graph has branches
    - mainline walk when linear
    - FAQ / OOB / probes from PathPlanConfig
    """
    if config is None:
        config = infer_path_plan_config(gb)
    g = gb.g
    flow_nodes = list(gb.flow_nodes or [])
    by_step = _branches_by_step(g)
    default = _default_branch_choices(by_step)
    all_branches = _branch_nodes(g)
    f4_ids = _f4_branch_ids(by_step)
    f6_ids = _f6_branch_ids(by_step)
    alt_by_step = _alternative_branch_ids(by_step)

    paths: List[Tuple[List[str], str]] = []
    seen: Set[str] = set()

    if config.is_branched:
        # --- Tier 1: cooperative F4 × F6 (8 variants) ---
        for f4 in f4_ids or [default.get(4)]:
            for f6 in f6_ids or [default.get(6)]:
                if not f4 or not f6:
                    continue
                choices = dict(default)
                choices[4] = f4
                choices[6] = f6
                _try_add(paths, seen, walk_path(g, flow_nodes, choices), "branch_grid")

        # --- Tier 2: alternative F1/F2/F3/F5 × F6 ---
        for alt_step, alt_bid in alt_by_step.items():
            for f6 in f6_ids or [default.get(6)]:
                if not f6:
                    continue
                choices = dict(default)
                choices[int(alt_step)] = alt_bid
                choices[6] = f6
                _try_add(paths, seen, walk_path(g, flow_nodes, choices), "branch_alt")

        # --- Tier 3: fill any branch/op still missing ---
        covered: Set[str] = set()
        for p, _desc in paths:
            covered |= set(branch_signature(p))
        for bid in all_branches:
            if bid in covered:
                continue
            step = g.nodes[bid].get("step") or _step_no(bid)
            if step is None:
                continue
            choices = dict(default)
            choices[int(step)] = bid
            candidate = walk_path(g, flow_nodes, choices)
            if candidate:
                covered |= set(branch_signature(candidate))
            _try_add(paths, seen, candidate, "branch_fill")
    else:
        _try_add(paths, seen, walk_path(g, flow_nodes, default) or ["START", "CLOSING", "END"], "mainline")

    faq_base = walk_path(g, flow_nodes, default) or ["START", "CLOSING", "END"]
    for nodes, desc in build_faq_coverage_paths(
        faq_base,
        faq_attach_steps=config.faq_attach_steps,
        instruction=gb.instruction,
    ):
        _try_add(paths, seen, nodes, desc)

    for oob in build_oob_coverage_paths(faq_base, oob_attach_steps=config.oob_attach_steps):
        _try_add(paths, seen, oob, "oob_coverage")

    if config.include_probes:
        for nodes, desc in build_constraint_probe_paths(faq_base):
            _try_add(paths, seen, nodes, desc)

    return paths


def uncovered_branches(gb: RuleGraphBuilder, paths: List[List[str] | Tuple[List[str], str]]) -> List[str]:
    covered: Set[str] = set()
    for item in paths:
        p = item[0] if isinstance(item, tuple) else item
        covered |= set(branch_signature(p))
    return sorted(set(_branch_nodes(gb.g)) - covered)
