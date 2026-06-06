from __future__ import annotations

import re
from typing import Any, Dict, List

from eval1.layer1.instruction_capabilities import instruction_has_retention_rails
from eval1.layer1.models import ConstraintType
from eval1.layer1.flow_branch_extract import extract_branches_from_block, iter_step_blocks
from eval1.layer2.instruction_injection import substitute_variables

_BOUNDARY_RE = re.compile(r"[「\"]([^」\"]+)[」\"]")


def _slots_from_instruction(instruction: Any, variable_values: Dict[str, str] | None = None) -> Dict[str, str]:
    slots = dict(variable_values or {})
    for name, vnode in dict(getattr(instruction, "variables", {}) or {}).items():
        val = str(getattr(vnode, "value", "") or "").strip()
        if val and name not in slots:
            slots[str(name)] = val
    return slots


def _boundary_phrase(instruction: Any) -> str:
    for c in list(getattr(instruction, "constraints", []) or []):
        text = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", ""))
        if "同事" in text:
            m = _BOUNDARY_RE.search(text)
            if m:
                return m.group(1).strip()
    return "我向同事确认后再回电给你。我现在能回答的先回答。"


def _refusal_hangup_phrase(instruction: Any) -> str:
    for c in list(getattr(instruction, "constraints", []) or []):
        text = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", ""))
        if "无法配送" in text and "挂断" in text:
            return text.strip()
    return "如果骑手坚持确实无法配送，安慰他们后挂断电话。"


def _closing_phrase(instruction: Any) -> str:
    parts: List[str] = ["主流程（Call Flow）完成后收口结束通话"]
    for c in list(getattr(instruction, "constraints", []) or []):
        text = str(getattr(c, "text", c) if not isinstance(c, dict) else c.get("text", "")).strip()
        if any(k in text for k in ("30", "字以内", "重复", "语气")):
            parts.append(text)
    return "；".join(parts[:3])


def _faq_intro(instruction: Any, slots: Dict[str, str]) -> str:
    knowledge = list(getattr(instruction, "knowledge_nodes", []) or [])
    lines = ["骑手追问业务细节；Bot 按 Knowledge Points (FAQ) 作答，并遵循「遵循对话流程和常见问题解答」。"]
    for kn in knowledge[:5]:
        kid = str(getattr(kn, "id", ""))
        text = substitute_variables(str(getattr(kn, "text", kn)), slots)
        if text.strip():
            lines.append(f"• {kid}：{text.strip()}")
    return "\n".join(lines)


def build_node_label_catalog(
    instruction: Any,
    variable_values: Dict[str, str] | None = None,
) -> Dict[str, str]:
    """FSM node id → data-grounded description (Opening / Call Flow / FAQ / Constraints)."""
    slots = _slots_from_instruction(instruction, variable_values)
    flow_steps = [substitute_variables(str(s), slots) for s in list(getattr(instruction, "flow_steps", []) or [])]
    opening = substitute_variables(str(getattr(instruction, "opening_line", "") or "").strip(), slots)
    retention = instruction_has_retention_rails(instruction)
    retain_step = flow_steps[2] if len(flow_steps) >= 3 else "挽留话术步骤"

    faq_subject = "商家" if not retention else "骑手"
    catalog: Dict[str, str] = {
        "START": f"Opening Line：{opening}" if opening else "Opening Line（开场白）",
        "END": "通话结束。",
        "CLOSING": _closing_phrase(instruction),
        "FAQ_NORMAL": (
            f"{faq_subject}追问业务细节；Bot 按 Knowledge / FAQ 作答。"
            if not retention
            else _faq_intro(instruction, slots)
        ),
        "FAQ_OOB": (
            f"{faq_subject}问及超出职责范围的问题；Bot 按 Constraints 回复边界话术："
            f"「{_boundary_phrase(instruction)}」，并将对话拉回主线。"
        ),
        "PROBE_D9_BUSY": "Constraints D9：用户表示忙；Bot 应回应「就1分钟，保证简短」后继续说明。",
        "PROBE_D10_DRIVE": "Constraints D10：用户表示开车；Bot 应礼貌说「稍后再打」后挂断。",
        "OBJECTION": (
            f"用户拒绝或质疑；进入异议处理，衔接：「{retain_step}」"
            if retention
            else "用户拒绝或质疑；Bot 简短回应后继续主流程。"
        ),
    }
    if retention:
        catalog["F3_RETAIN"] = f"Call Flow 第 3 步（挽留）：「{retain_step}」"
        catalog["OBJ_FINAL"] = f"Constraints：「{_refusal_hangup_phrase(instruction)}」"

    for i, step in enumerate(flow_steps, start=1):
        catalog[f"F{i}"] = f"Call Flow 第 {i} 步：「{step}」"

    raw = str(getattr(instruction, "raw_text", "") or "")
    from eval1.layer1.flow_branch_model import parse_instruction_branches

    for br in parse_instruction_branches(raw):
        catalog[br.branch_id] = (
            f"分支·F{br.step_no}"
            + (f"·{br.section}" if br.section else "")
            + f"：若{br.condition} → {br.action}"
        )
    for step_no, block in iter_step_blocks(raw):
        for i, (cond, act) in enumerate(extract_branches_from_block(block), start=1):
            bid = f"branch::{step_no}::{i}"
            if bid not in catalog:
                catalog[bid] = f"分支·F{step_no}：若{cond} → {act}"

    return catalog


def path_category_tag(path_nodes: List[str]) -> str:
    from eval1.layer1.path_probe import PROBE_D10_DRIVE, PROBE_D9_BUSY

    if PROBE_D10_DRIVE in path_nodes:
        return "probe_drive_d10"
    if PROBE_D9_BUSY in path_nodes:
        return "probe_busy_d9"
    if "OBJ_FINAL" in path_nodes:
        return "retention_failed"
    if "FAQ_OOB" in path_nodes:
        return "contains_oob_faq"
    if "FAQ_NORMAL" in path_nodes:
        from eval1.layer1.faq_step_context import faq_interrupt_flow_step

        step = faq_interrupt_flow_step(path_nodes)
        if step:
            return f"faq_after_{step.lower()}"
        return "contains_faq_interrupt"
    if "F3_RETAIN" in path_nodes:
        return "contains_retention"
    if any(str(n).startswith("op::") for n in path_nodes):
        return "contains_guided_setup"
    if any(str(n).startswith("branch::") for n in path_nodes):
        return "contains_flow_branch"
    return "standard_completion"


def path_category_label(path_nodes: List[str]) -> str:
    tags = {
        "standard_completion": "标准顺流程完成",
        "contains_flow_branch": "含条件分支路径",
        "contains_guided_setup": "含分步引导开通/配置",
        "contains_faq_interrupt": "含 FAQ 中断后继续",
        "faq_after_f2": "F2 后 FAQ 业务追问",
        "faq_after_f3": "F3 后 FAQ 业务追问",
        "faq_after_f4": "F4 后 FAQ 业务追问",
        "faq_after_f5": "F5 后 FAQ 业务追问",
        "faq_after_f7": "F7 后 FAQ 业务追问",
        "probe_busy_d9": "D9 忙场景探针",
        "probe_drive_d10": "D10 开车场景探针",
        "contains_retention": "含挽留跳转",
        "contains_oob_faq": "含越权/跑题处理",
        "retention_failed": "挽留失败终止",
    }
    return tags.get(path_category_tag(path_nodes), "自定义路径")


_RULE_TYPE_LABELS = {
    ConstraintType.FLOW: "流程",
    ConstraintType.DIALOGUE: "对话",
    ConstraintType.BOUNDARY: "边界",
    ConstraintType.KNOWLEDGE: "知识",
    ConstraintType.ROLE: "角色",
    ConstraintType.VARIABLE: "变量",
}


def _rule_type_label(constraint_type: Any) -> str:
    if isinstance(constraint_type, ConstraintType):
        return _RULE_TYPE_LABELS.get(constraint_type, "规则")
    try:
        return _RULE_TYPE_LABELS.get(ConstraintType(str(constraint_type)), "规则")
    except ValueError:
        return "规则"


def _truncate_rule_text(text: str, limit: int = 72) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def build_rule_label_catalog(
    instruction: Any,
    variable_values: Dict[str, str] | None = None,
) -> Dict[str, str]:
    """Rule id → short human-readable label (type + text snippet)."""
    slots = _slots_from_instruction(instruction, variable_values)
    catalog: Dict[str, str] = {}
    for c in list(getattr(instruction, "constraints", []) or []):
        cid = str(getattr(c, "id", "") or "")
        if not cid:
            continue
        ctype = getattr(c, "type", ConstraintType.DIALOGUE)
        text = substitute_variables(str(getattr(c, "text", c)), slots)
        kind = _rule_type_label(ctype)
        catalog[cid] = f"{kind}：{_truncate_rule_text(text)}"
    for kn in list(getattr(instruction, "knowledge_nodes", []) or []):
        kid = str(getattr(kn, "id", "") or "")
        if not kid or kid in catalog:
            continue
        text = substitute_variables(str(getattr(kn, "text", kn)), slots)
        catalog[kid] = f"知识：{_truncate_rule_text(text)}"
    flow_steps = list(getattr(instruction, "flow_steps", []) or [])
    for i, step in enumerate(flow_steps, start=1):
        fid = f"F{i}"
        if fid in catalog:
            continue
        text = substitute_variables(str(step), slots)
        catalog[fid] = f"流程：{_truncate_rule_text(text)}"
    return catalog


def describe_path_rules(
    activated_rules: List[str],
    instruction: Any,
    variable_values: Dict[str, str] | None = None,
) -> str:
    rules = [str(r) for r in (activated_rules or []) if str(r).strip()]
    if not rules:
        return "本路径未激活额外规则约束。"
    catalog = build_rule_label_catalog(instruction, variable_values)
    lines = [f"【激活规则 · 共 {len(rules)} 条】"]
    for rid in rules:
        detail = catalog.get(rid, "")
        if detail:
            lines.append(f"· {rid}（{detail}）")
        else:
            lines.append(f"· {rid}")
    return "\n".join(lines)


def knowledge_target_label(
    instruction: Any,
    kid: str,
    variable_values: Dict[str, str] | None = None,
) -> str:
    """Short display for a path's target knowledge node, e.g. K3（知识：…）."""
    if not kid:
        return ""
    catalog = build_rule_label_catalog(instruction, variable_values)
    detail = catalog.get(kid, kid)
    return f"{kid}（{detail}）"


def scenario_target_label(
    instruction: Any,
    did: str,
    variable_values: Dict[str, str] | None = None,
) -> str:
    """Short display for a path's target constraint scenario, e.g. D9（对话：…）."""
    if not did:
        return ""
    catalog = build_rule_label_catalog(instruction, variable_values)
    detail = catalog.get(did, did)
    return f"{did}（{detail}）"


def _scenario_short_label(did: str) -> str:
    if did == "D9":
        return "D9·忙"
    if did == "D10":
        return "D10·开车"
    return did


def format_path_sequence(
    path_nodes: List[str],
    target_knowledge_id: str = "",
    target_scenario_id: str = "",
) -> str:
    from eval1.layer1.path_probe import PROBE_CONSTRAINT_MAP, is_probe_node

    parts: List[str] = []
    for nid in path_nodes:
        if nid == "FAQ_NORMAL" and target_knowledge_id:
            parts.append(f"FAQ_NORMAL→{target_knowledge_id}")
        elif is_probe_node(nid):
            did = target_scenario_id or PROBE_CONSTRAINT_MAP.get(str(nid), "")
            parts.append(f"{nid}→{did}" if did else str(nid))
        else:
            parts.append(str(nid))
    return " → ".join(parts)


def describe_path_flow(
    path_nodes: List[str],
    instruction: Any,
    variable_values: Dict[str, str] | None = None,
    target_knowledge_id: str = "",
    target_scenario_id: str = "",
) -> str:
    from eval1.layer1.path_probe import is_probe_node, probe_constraint_id

    catalog = build_node_label_catalog(instruction, variable_values)
    k_label = knowledge_target_label(instruction, target_knowledge_id, variable_values)
    d_label = scenario_target_label(instruction, target_scenario_id, variable_values)
    lines: List[str] = []
    step_no = 0
    for nid in path_nodes:
        if nid in {"START", "END"}:
            continue
        step_no += 1
        label = catalog.get(nid, nid)
        if nid == "FAQ_NORMAL" and k_label:
            label = f"{label}\n   ↳ 覆盖知识点：{k_label}"
        if is_probe_node(nid):
            did = target_scenario_id or probe_constraint_id(nid)
            if did:
                sl = scenario_target_label(instruction, did, variable_values) or did
                label = f"{label}\n   ↳ 约束场景：{sl}"
        lines.append(f"{step_no}. 【{nid}】{label}")
    return "\n".join(lines)


def enrich_path_dict(
    path_dict: Dict[str, Any],
    instruction: Any,
    variable_values: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    from eval1.layer1.faq_step_context import faq_path_desc_tag
    from eval1.layer1.path_probe import is_probe_node, probe_constraint_for_path, scenario_path_desc_tag
    from eval1.layer2.step_speakable import describe_skipped_branches

    nodes = list(path_dict.get("nodes") or [])
    path_dict = dict(path_dict)
    desc = str(path_dict.get("description") or "")

    target_k = str(path_dict.get("target_knowledge_id") or "").strip()
    if not target_k:
        target_k = faq_path_desc_tag(desc)
        if target_k:
            path_dict["target_knowledge_id"] = target_k

    target_d = str(path_dict.get("target_scenario_id") or "").strip()
    if not target_d:
        target_d = scenario_path_desc_tag(desc) or probe_constraint_for_path(nodes)
        if target_d:
            path_dict["target_scenario_id"] = target_d

    catalog = build_node_label_catalog(instruction, variable_values)
    path_dict["node_labels"] = {nid: catalog.get(nid, nid) for nid in nodes if nid in catalog}
    k_label = knowledge_target_label(instruction, target_k, variable_values)
    d_label = scenario_target_label(instruction, target_d, variable_values)
    if target_k and k_label:
        path_dict["knowledge_target_label"] = k_label
        if "FAQ_NORMAL" in nodes:
            base = path_dict["node_labels"].get("FAQ_NORMAL", catalog.get("FAQ_NORMAL", "FAQ 业务追问"))
            path_dict["node_labels"]["FAQ_NORMAL"] = f"{base}（测 {k_label}）"
    if target_d and d_label:
        path_dict["scenario_target_label"] = d_label
        for nid in nodes:
            if is_probe_node(nid):
                base = path_dict["node_labels"].get(nid, catalog.get(nid, nid))
                path_dict["node_labels"][nid] = f"{base}（测 {d_label}）"

    path_dict["flow_description"] = describe_path_flow(
        nodes,
        instruction,
        variable_values,
        target_knowledge_id=target_k,
        target_scenario_id=target_d,
    )
    path_dict["path_sequence_display"] = format_path_sequence(nodes, target_k, target_d)
    skipped = describe_skipped_branches(nodes, instruction)
    if skipped:
        path_dict["branch_notes"] = skipped
    activated = [str(r) for r in list(path_dict.get("activated_rules") or []) if str(r).strip()]
    rule_catalog = build_rule_label_catalog(instruction, variable_values)
    path_dict["rule_labels"] = {rid: rule_catalog.get(rid, rid) for rid in activated}
    path_dict["rules_description"] = describe_path_rules(activated, instruction, variable_values)
    base_category = path_category_label(nodes)
    suffix_parts = [p for p in (target_k, target_d) if p]
    path_dict["category_label"] = f"{base_category} · {' · '.join(suffix_parts)}" if suffix_parts else base_category
    if not str(path_dict.get("description") or "").strip():
        path_dict["description"] = path_category_tag(nodes)
    return path_dict
