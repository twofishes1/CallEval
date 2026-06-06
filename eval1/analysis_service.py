from __future__ import annotations

import re
from typing import Any, Dict, List

from eval1.data_loader import get_dataset, list_dataset_summaries
from eval1.layer1.parser_agent import InstructionParserAgent
from eval1.layer1.flow_branch_model import flow_branches_by_step_for_instruction
from eval1.layer1.fsm_viz_builder import build_goal_fsm_meta, build_path_fsm_projection
from eval1.layer1.path_descriptions import build_node_label_catalog
from eval1.layer1.path_enumerator import PathEnumerator
from eval1.layer1.rule_graph import RuleGraphBuilder


# Mirror frontend kgLayout.js swim-lane layout
_COL_META = 64
_COL_LEFT = 168
_COL_FLOW = 320
_COL_BRANCH = 448
_COL_TRANSITION = 560
_COL_RIGHT = 680
_ROW_STEP = 68
_GROUP_GAP = 28
_START_Y = 72

_ATTACH_KIND_ORDER_LEFT = ("objection", "dialogue", "boundary", "other_left")
_ATTACH_KIND_ORDER_RIGHT = ("knowledge", "retention", "flow_aux", "other_right")


def _sort_key(nid: str) -> tuple:
    m = re.match(r"^([A-Za-z_]+)(\d+)", nid or "")
    if m:
        return (m.group(1), int(m.group(2)))
    return (nid, 0)


def _flow_order(nid: str) -> int:
    m = re.match(r"^F(\d+)", nid or "", re.I)
    return int(m.group(1)) if m else 9999


def _is_flow_step_id(nid: str) -> bool:
    return bool(re.match(r"^F\d+$", nid or "", re.I)) and "RETAIN" not in nid


def _is_branch_node_id(nid: str) -> bool:
    return str(nid).startswith("branch::") or str(nid).startswith("op::")


def _branch_step(nid: str) -> int:
    m = re.match(r"^(?:branch|op)::(\d+)::", str(nid))
    return int(m.group(1)) if m else 9999


def _bucket(ntype: str, nid: str) -> str:
    if _is_branch_node_id(nid) or ntype in ("flow_branch", "op_step"):
        return "branch"
    if ntype == "meta":
        return "meta"
    if ntype == "flow_step":
        return "flow" if _is_flow_step_id(nid) else "attach"
    if ntype == "transition":
        return "transition"
    return "attach"


def _attach_kind(nid: str, data: Dict[str, Any]) -> str:
    ntype = str(data.get("node_type", ""))
    ctype = str(data.get("constraint_type", "")).lower()
    if re.match(r"^K\d", nid, re.I) or ntype == "knowledge" or ctype == "knowledge":
        return "knowledge"
    if re.match(r"^D\d", nid, re.I) or ctype in ("dialogue", "dial"):
        return "dialogue"
    if re.match(r"^B\d", nid, re.I) or ctype == "boundary":
        return "boundary"
    if re.match(r"^R\d", nid, re.I) or "RETAIN" in nid:
        return "retention"
    if re.match(r"^F", nid, re.I):
        return "flow_aux"
    if re.match(r"^(FAQ|OBJ)", nid, re.I):
        return "objection"
    return "other_left"


def _distribute_ys(count: int, top: int, bottom: int) -> List[int]:
    if count <= 0:
        return []
    if count == 1:
        return [(top + bottom) // 2]
    step = (bottom - top) / max(count - 1, 1)
    return [int(top + i * step) for i in range(count)]


def _stack_attach_groups(
    groups: Dict[str, List[str]],
    kind_order: tuple[str, ...],
    col_x: int,
    start_y: int,
) -> tuple[Dict[str, tuple[int, int]], int]:
    positions: Dict[str, tuple[int, int]] = {}
    y = start_y
    for kind in kind_order:
        items = sorted(groups.get(kind, []), key=_sort_key)
        if not items:
            continue
        for nid in items:
            positions[nid] = (col_x, y)
            y += _ROW_STEP
        y += _GROUP_GAP
    height = max(0, y - start_y - _GROUP_GAP)
    return positions, height


def _layout_compact_viz(gb: RuleGraphBuilder) -> Dict[str, tuple[int, int]]:
    """Type-clustered swim lanes (aligned with frontend kgLayout.js)."""
    buckets: Dict[str, List[str]] = {
        "meta": [],
        "flow": [],
        "branch": [],
        "transition": [],
        "attach": [],
    }
    node_data: Dict[str, Dict[str, Any]] = {}
    for nid, data in gb.g.nodes(data=True):
        node_data[nid] = dict(data)
        ntype = str(data.get("node_type", "meta"))
        b = _bucket(ntype, nid)
        buckets[b].append(nid)

    buckets["flow"].sort(key=_flow_order)

    attach_groups: Dict[str, List[str]] = {}
    for nid in buckets["attach"]:
        kind = _attach_kind(nid, node_data.get(nid, {}))
        if kind == "other_left":
            if re.match(r"^K", nid, re.I):
                kind = "knowledge"
            elif re.match(r"^R", nid, re.I):
                kind = "retention"
            else:
                kind = "other_right"
        attach_groups.setdefault(kind, []).append(nid)

    positions: Dict[str, tuple[int, int]] = {}
    left_pos, left_h = _stack_attach_groups(
        attach_groups, _ATTACH_KIND_ORDER_LEFT, _COL_LEFT, _START_Y
    )
    right_pos, right_h = _stack_attach_groups(
        attach_groups, _ATTACH_KIND_ORDER_RIGHT, _COL_RIGHT, _START_Y
    )
    positions.update(left_pos)
    positions.update(right_pos)

    side_h = max(left_h, right_h, _ROW_STEP * 2)
    flow_ids = buckets["flow"]
    flow_top = _START_Y
    flow_bottom = _START_Y + max(side_h, (len(flow_ids) - 1) * _ROW_STEP)
    flow_ys = _distribute_ys(len(flow_ids), flow_top, flow_bottom)
    for nid, y in zip(flow_ids, flow_ys):
        positions[nid] = (_COL_FLOW, y)

    branches_by_step: Dict[int, List[str]] = {}
    for nid in buckets["branch"]:
        branches_by_step.setdefault(_branch_step(nid), []).append(nid)
    for step_no, branch_ids in branches_by_step.items():
        parent = f"F{step_no}"
        anchor_y = positions.get(parent, (_COL_FLOW, flow_top))[1]
        ordered = sorted(branch_ids, key=_sort_key)
        spread = int(_ROW_STEP * 0.72) if len(ordered) > 1 else 0
        start_y = anchor_y - ((len(ordered) - 1) * spread) // 2
        for i, bid in enumerate(ordered):
            positions[bid] = (_COL_BRANCH, start_y + i * spread)

    spine_top = flow_ys[0] if flow_ys else flow_top
    spine_bottom = flow_ys[-1] if flow_ys else flow_bottom
    pad = int(_ROW_STEP * 1.1)

    meta_order = ["GLOBAL_DIALOGUE", "GLOBAL_BOUNDARY", "START", "CLOSING", "END"]
    meta_y = spine_top - int(pad * 1.5)
    for nid in sorted(buckets["meta"], key=lambda x: (meta_order.index(x) if x in meta_order else 99, x)):
        if nid == "START":
            y = spine_top - int(pad * 0.8)
        elif nid == "CLOSING":
            y = spine_bottom + int(pad * 0.5)
        elif nid == "END":
            y = spine_bottom + int(pad * 1.1)
        else:
            y = meta_y
            meta_y -= int(_ROW_STEP * 0.85)
        positions[nid] = (_COL_META, y)

    trans = sorted(buckets["transition"], key=_sort_key)
    if len(trans) <= 6:
        for i, nid in enumerate(trans):
            y = spine_top + int((spine_bottom - spine_top) * (i + 1) / max(len(trans) + 1, 1))
            positions[nid] = (_COL_TRANSITION, y)
    else:
        for nid, y in zip(trans, _distribute_ys(len(trans), spine_top, spine_bottom)):
            positions[nid] = (_COL_TRANSITION, y)

    return positions


def _to_viz(gb: RuleGraphBuilder) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    positions = _layout_compact_viz(gb)

    for nid, data in gb.g.nodes(data=True):
        ntype = str(data.get("node_type", "meta"))
        x, y = positions.get(nid, (120, 80))
        kind = "dial"
        if ntype == "flow_step":
            kind = "flow"
        elif ntype == "knowledge":
            kind = "know"
        elif ntype == "constraint":
            ctype = str(data.get("constraint_type", "")).lower()
            if ctype == "boundary":
                kind = "boun"
            elif ctype == "flow":
                kind = "flow"
            elif ctype == "knowledge":
                kind = "know"
            else:
                kind = "dial"
        elif ntype == "meta":
            kind = "role" if nid in {"START", "END"} else "dial"
        elif ntype == "flow_branch":
            kind = "branch"
        elif ntype == "op_step":
            kind = "branch"

        text = str(data.get("text") or data.get("label") or nid)
        label = str(nid)
        if ntype == "flow_branch":
            text = str(data.get("text") or f"若{data.get('condition', '')}→{data.get('action', '')}")
            label = f"BR{data.get('step', '')}-{data.get('index', '')}"
        elif ntype == "op_step":
            text = str(data.get("text") or data.get("label") or nid)
            label = f"OP{data.get('step', '')}-{data.get('index', '')}"

        nodes.append(
            {
                "id": nid,
                "label": label,
                "type": kind,
                "node_type": ntype,
                "text": text,
                "x": x,
                "y": y,
            }
        )
    for u, v, data in gb.g.edges(data=True):
        edges.append(
            {
                "from": str(u),
                "to": str(v),
                "type": str(data.get("edge_type", "requires")),
                "label": str(data.get("guard_expr", data.get("edge_type", ""))),
                "edge_confidence": float(data.get("edge_confidence", 0.0)),
                "guard_expr": str(data.get("guard_expr", "")),
            }
        )
    return {"nodes": nodes, "edges": edges}


async def build_layer1_analysis(dataset_id: str) -> Dict[str, Any]:
    d = get_dataset(dataset_id)
    if not d:
        raise ValueError(f"dataset not found: {dataset_id}")
    parser = InstructionParserAgent()
    parsed = await parser.parse(
        dataset_id,
        d["raw_instruction"],
        variable_values=(d.get("variable_values") or {}),
    )
    gb = RuleGraphBuilder.build_from_instruction(parsed)
    conflicts = [c.__dict__ for c in gb.detect_conflicts()]
    paths = [p.model_dump() for p in PathEnumerator(gb).enumerate_paths()]
    variable_values = dict(d.get("variable_values") or {})
    node_label_catalog = build_node_label_catalog(parsed, variable_values)
    for nid, ndata in gb.g.nodes(data=True):
        if ndata.get("node_type") in ("flow_branch", "op_step"):
            node_label_catalog[str(nid)] = str(ndata.get("text") or ndata.get("label") or nid)
    viz = _to_viz(gb)
    goal_fsm = build_goal_fsm_meta(gb, parsed)
    paths_out: List[Dict[str, Any]] = []
    for p in paths:
        pd = dict(p)
        pd["fsm_projection"] = build_path_fsm_projection(
            list(pd.get("nodes") or []),
            pd.get("node_labels") or node_label_catalog,
            gb,
            target_knowledge_id=str(pd.get("target_knowledge_id") or ""),
            target_scenario_id=str(pd.get("target_scenario_id") or ""),
            instruction=parsed,
            variable_values=variable_values,
        )
        paths_out.append(pd)
    parsed_out = parsed.model_dump()
    parsed_out["flow_branches_by_step"] = flow_branches_by_step_for_instruction(parsed)
    return {
        "dataset_id": dataset_id,
        "dataset_name": d.get("name", dataset_id),
        "variable_values": variable_values,
        "node_label_catalog": node_label_catalog,
        "parsed": parsed_out,
        "summary": {
            "node_count": len(viz["nodes"]),
            "edge_count": len(viz["edges"]),
            "path_count": len(paths),
            "conflict_count": len(conflicts),
        },
        "kg_viz": viz,
        "goal_fsm": goal_fsm,
        "conflicts": conflicts,
        "paths": paths_out,
    }


def list_eval1_datasets() -> List[Dict[str, Any]]:
    return list_dataset_summaries()
