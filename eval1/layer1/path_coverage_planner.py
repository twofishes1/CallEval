from __future__ import annotations

from typing import List, Tuple

from eval1.layer1.path_coverage_builder import build_minimal_coverage_paths, path_dedupe_key
from eval1.layer1.path_plan_config import PathPlanConfig
from eval1.layer1.path_linear_curator import curate_retention_flow_paths
from eval1.layer1.rule_graph import RuleGraphBuilder

PathItem = Tuple[List[str], List[str], int, str, float]


def plan_coverage_paths(
    gb: RuleGraphBuilder,
    config: PathPlanConfig,
    *,
    linear_dfs_pool: List[PathItem],
) -> List[PathItem]:
    """
    Unified Layer1 coverage planner (single entry for all tasks).

    Pipeline:
      1. Structured coverage — branch grid / mainline + FAQ + OOB + probes (shared builder)
      2. Linear retention pool — optional DFS candidates + curator selectors
      3. Semantic dedupe + cap

    Branched tasks use stage 1 only (stage 2 skipped).
    Linear retention tasks merge stage 1 supplements into stage 2 pool.
    """
    structured_paths = build_minimal_coverage_paths(gb, config)
    structured_items: List[PathItem] = [_item_from_path(gb, p, desc) for p, desc in structured_paths]

    if config.is_branched or not config.include_retention_variants:
        return _dedupe_items(structured_items)[: config.max_paths]

    pool = list(linear_dfs_pool)
    seen_keys = {_path_key(item[0]) for item in pool}
    for item in structured_items:
        key = _path_key(item[0])
        if key not in seen_keys:
            seen_keys.add(key)
            pool.append(item)

    curated = curate_retention_flow_paths(pool, instruction=gb.instruction)
    return curated[: config.max_paths]


def _path_key(path: List[str]) -> tuple:
    return tuple(path)


def _dedupe_items(items: List[PathItem]) -> List[PathItem]:
    out: List[PathItem] = []
    seen: set[str] = set()
    for item in items:
        key = path_dedupe_key(item[0], str(item[3] or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _item_from_path(gb: RuleGraphBuilder, path: List[str], desc: str = "structured_coverage") -> PathItem:
    flow_len = len(gb.flow_nodes or [])
    cost = _estimate_turn_cost(gb, path)
    branched = any(str(n).startswith(("branch::", "op::")) for n in path)
    base_turns = max(24, cost + (6 if branched else flow_len * 2))
    return (
        path,
        _activated_rules(gb, path),
        base_turns,
        desc,
        0.85,
    )


def _estimate_turn_cost(gb: RuleGraphBuilder, path: List[str]) -> int:
    node_turn_cost = {
        "flow_step": 2,
        "flow_branch": 1,
        "op_step": 1,
        "transition": 3,
        "meta": 1,
        "knowledge": 1,
    }
    cost = 0
    g = gb.g
    for n in path:
        if n not in g:
            cost += 1
            continue
        ntype = str(g.nodes[n].get("node_type", "meta"))
        cost += node_turn_cost.get(ntype, 1)
    return cost


def _activated_rules(gb: RuleGraphBuilder, path: List[str]) -> List[str]:
    ids: List[str] = []
    flow_set = set(path)
    for c in gb.instruction.constraints:
        cid = c.id
        if cid.startswith("D") or cid.startswith("B"):
            ids.append(cid)
            continue
        if cid.startswith("F") and cid in flow_set:
            ids.append(cid)
            continue
        if cid.startswith("K") and ("FAQ_NORMAL" in flow_set or "FAQ_OOB" in flow_set):
            ids.append(cid)
    for n in path:
        if str(n).startswith("branch::"):
            ids.append(str(n))
    return sorted(set(ids))
