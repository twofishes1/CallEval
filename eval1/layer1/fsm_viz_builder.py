from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx

from eval1.layer1.instruction_capabilities import instruction_has_retention_rails
from eval1.layer1.rule_graph import RuleGraphBuilder

_GUARD_LABELS: Dict[str, str] = {
    "true": "开场",
    "flow_progress": "步骤完成→下一步",
    "all_steps_done": "主流程完成",
    "closing_done": "收口结束",
    "user_refusal": "用户拒绝/异议",
    "user_asks_faq": "用户FAQ提问",
    "user_oob_question": "越权/跑题提问",
    "early_refusal": "早期拒绝→挽留",
    "mid_refusal": "中途拒绝→挽留",
    "still_refuse": "仍拒绝→终止",
    "terminate": "终止通话",
    "redirect_and_close": "拉回并收口",
}


def _infer_fsm_node_type(nid: str, node_type: str = "") -> str:
    nt = str(node_type or "")
    u = str(nid or "").upper()
    if u == "START":
        return "start"
    if u == "END":
        return "end"
    if u == "CLOSING":
        return "closing"
    if u in {"OBJECTION", "OBJ_FINAL"}:
        return "objection"
    if u == "FAQ_NORMAL":
        return "faq_normal"
    if u == "FAQ_OOB":
        return "faq_oob"
    if u.startswith("PROBE_"):
        return "scenario_probe"
    if u == "F3_RETAIN":
        return "return_to_flow"
    if nt == "flow_branch" or str(nid).startswith("branch::"):
        return "choice_branch"
    if nt == "op_step" or str(nid).startswith("op::"):
        return "op_step"
    if u.startswith("F") and u[1:].isdigit():
        return "flow_step"
    return "other"


def _short_branch_label(nid: str, data: Dict[str, Any]) -> str:
    if str(nid).startswith("branch::"):
        return f"BR{data.get('step', '')}-{data.get('index', '')}"
    if str(nid).startswith("op::"):
        return f"OP{data.get('step', '')}-{data.get('index', '')}"
    return str(nid)


def _edge_trigger_label(g: nx.DiGraph, u: str, v: str, data: Dict[str, Any]) -> str:
    et = str(data.get("edge_type", ""))
    guard = str(data.get("guard_expr", "") or "")

    if str(v).startswith("branch::"):
        return "条件分支"
    if str(u).startswith("branch::"):
        node = dict(g.nodes.get(u, {}))
        cond = str(node.get("condition") or "").strip()
        if cond:
            return f"若{cond[:12]}{'…' if len(cond) > 12 else ''}"
        return "选择后跳转"
    if str(u).startswith("op::"):
        return "操作引导"

    if guard.startswith("resume_before:"):
        return "回到未执行步骤"
    if guard in _GUARD_LABELS:
        return _GUARD_LABELS[guard]

    if et == "sequence":
        return "顺序推进"
    if et == "branch":
        return "中断分支"
    if et == "goto":
        return "跳转"
    if et == "retention_jump":
        return "进入挽留"
    if et == "guides":
        return "操作引导"
    if et == "path_step":
        return "路径推进"
    return et or "转移"


def build_goal_fsm_meta(gb: RuleGraphBuilder, instruction: Any) -> Dict[str, Any]:
    """Cytoscape-compatible FSM meta for Layer1 GoalFsmGraph (global rule graph view)."""
    g = gb.g
    flow_steps = list(getattr(instruction, "flow_steps", []) or [])
    retention = instruction_has_retention_rails(instruction)
    node_ids: List[str] = []
    nodes: List[Dict[str, Any]] = []

    def _push(nid: str) -> None:
        if nid not in g or nid in node_ids:
            return
        node_ids.append(nid)
        data = dict(g.nodes[nid])
        ntype = _infer_fsm_node_type(nid, str(data.get("node_type", "")))
        label = str(nid)
        step_index = None
        if ntype == "flow_step" and nid.startswith("F") and nid[1:].isdigit():
            idx = int(nid[1:])
            step_index = idx
            label = f"F{idx}"
        elif ntype in ("choice_branch", "op_step"):
            label = _short_branch_label(nid, data)
        nodes.append(
            {
                "id": nid,
                "label": label,
                "type": ntype,
                "step_index": step_index,
            }
        )

    for nid in ["START", *gb.flow_nodes, "CLOSING", "END"]:
        _push(nid)
    for nid in ["OBJECTION", "FAQ_NORMAL", "FAQ_OOB"]:
        _push(nid)
    if retention:
        for nid in ["F3_RETAIN", "OBJ_FINAL"]:
            _push(nid)
    for nid, data in g.nodes(data=True):
        if data.get("node_type") in ("flow_branch", "op_step"):
            _push(str(nid))

    node_set = set(node_ids)
    edges: List[Dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for u, v, data in g.edges(data=True):
        if u not in node_set or v not in node_set:
            continue
        et = str(data.get("edge_type", ""))
        if et not in {"sequence", "branch", "goto", "retention_jump", "guides"}:
            continue
        key = (u, v, et)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(
            {
                "from": str(u),
                "to": str(v),
                "label": _edge_trigger_label(g, str(u), str(v), data),
                "trigger_type": et,
                "virtual": et in {"retention_jump", "goto"} and u in {"F3_RETAIN", "FAQ_NORMAL"},
            }
        )

    return {"nodes": nodes, "edges": edges}


def build_path_fsm_projection(
    path_nodes: List[str],
    node_labels: Dict[str, str] | None = None,
    gb: RuleGraphBuilder | None = None,
    *,
    target_knowledge_id: str = "",
    target_scenario_id: str = "",
    instruction: Any | None = None,
    variable_values: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Linear path → FSM projection with trigger labels on edges."""
    from eval1.layer1.path_descriptions import _scenario_short_label, knowledge_target_label, scenario_target_label
    from eval1.layer1.path_probe import is_probe_node, probe_constraint_id

    labels = dict(node_labels or {})
    g = gb.g if gb is not None else None
    target_k = str(target_knowledge_id or "").strip()
    target_d = str(target_scenario_id or "").strip()
    k_detail = ""
    d_detail = ""
    if target_k and instruction is not None:
        k_detail = knowledge_target_label(instruction, target_k, variable_values)
    if target_d and instruction is not None:
        d_detail = scenario_target_label(instruction, target_d, variable_values)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for nid in path_nodes:
        short = str(nid)
        if str(nid).startswith("branch::"):
            parts = str(nid).split("::")
            if len(parts) >= 4:
                short = f"BR{parts[1]}-{parts[-1]}"
            elif len(parts) >= 3:
                short = f"BR{parts[1]}-{parts[2]}"
        elif str(nid).startswith("op::"):
            parts = str(nid).split("::")
            if len(parts) >= 5:
                short = f"OP{parts[1]}-{parts[-2]}.{parts[-1]}"
            elif len(parts) >= 3:
                short = f"OP{parts[1]}-{parts[2]}"
        elif str(nid).upper() == "FAQ_NORMAL" and target_k:
            short = f"FAQ·{target_k}"
        elif is_probe_node(nid):
            did = target_d or probe_constraint_id(nid)
            short = _scenario_short_label(did) if did else short

        desc = labels.get(nid, short)
        if str(nid).upper() == "FAQ_NORMAL" and k_detail:
            desc = k_detail if k_detail not in desc else desc
        if is_probe_node(nid) and d_detail:
            desc = d_detail if d_detail not in desc else desc
        if len(desc) > 72:
            desc = desc[:70] + "…"

        node_entry: Dict[str, Any] = {
            "id": str(nid),
            "label": short,
            "type": _infer_fsm_node_type(str(nid)),
            "detail": desc if desc != short else "",
        }
        if str(nid).upper() == "FAQ_NORMAL" and target_k:
            node_entry["knowledge_id"] = target_k
        if is_probe_node(nid):
            did = target_d or probe_constraint_id(nid)
            if did:
                node_entry["scenario_id"] = did
        nodes.append(node_entry)

    for i in range(len(path_nodes) - 1):
        u, v = str(path_nodes[i]), str(path_nodes[i + 1])
        edge_data: Dict[str, Any] = {"edge_type": "path_step", "guard_expr": ""}
        if g is not None and g.has_edge(u, v):
            edge_data = dict(g.edges[u, v])
        edge_label = _edge_trigger_label(g, u, v, edge_data) if g is not None else "路径推进"
        if v.upper() == "FAQ_NORMAL" and target_k:
            edge_label = f"测 {target_k} FAQ"
        elif is_probe_node(v):
            did = target_d or probe_constraint_id(v)
            if did:
                edge_label = f"测 {did} 场景"
        edges.append(
            {
                "from": u,
                "to": v,
                "label": edge_label,
                "trigger_type": str(edge_data.get("edge_type", "path_step")),
                "virtual": False,
            }
        )
    return {"nodes": nodes, "edges": edges}
