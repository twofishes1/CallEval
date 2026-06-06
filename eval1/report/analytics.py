"""Scoring analytics aggregation for API / reports."""

from __future__ import annotations

from typing import Any, Dict, List

VIOLATION_TYPE_LABELS = {
    "flow_miss": "流程未覆盖",
    "dialogue_length": "话术超长",
    "hard_boundary": "硬边界",
    "flow_incomplete": "流程未完成",
}

RULE_ID_HINTS = {
    "D_LEN": "每轮 Bot 话术不超过 30 字（Opening Line 除外）",
    "B*": "边界约束：不得宣称不支持的能力",
}


def _enrich_rule_description(constraint_id: str, text: str, violation_type: str) -> str:
    cid = str(constraint_id or "?")
    raw = str(text or "").strip()
    vt = str(violation_type or "")
    if cid in RULE_ID_HINTS:
        return RULE_ID_HINTS[cid]
    if raw and not raw.lower().startswith("path not fully") and not raw.lower().startswith("flow adherence"):
        return raw
    import re

    if re.match(r"^P\d+$", cid, re.I):
        return f"测试路径 {cid} 未按设计步骤完整执行（路径覆盖不足）"
    if vt in VIOLATION_TYPE_LABELS:
        label = VIOLATION_TYPE_LABELS[vt]
        return f"{label}：{raw}" if raw else f"{label}（{cid}）"
    return raw or vt or cid


PERSONA_LABELS = {
    "cooperative": "配合型",
    "impatient": "急躁型",
    "resistant": "抵触型",
    "questioning": "质疑型",
    "ignorant": "懵懂型",
    "off_topic": "跑题型",
}


def build_scoring_analytics(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    rule_map: Dict[str, Dict[str, Any]] = {}
    type_map: Dict[str, int] = {}
    persona_map: Dict[str, Dict[str, Any]] = {}
    termination_map: Dict[str, int] = {}
    total_violations = 0
    cases_with_violations = 0

    for r in reports or []:
        persona = str(r.get("persona_type") or "unknown")
        pe = persona_map.setdefault(
            persona,
            {
                "persona_type": persona,
                "label": PERSONA_LABELS.get(persona, persona),
                "count": 0,
                "total_score": 0.0,
                "violations": 0,
            },
        )
        pe["count"] += 1
        pe["total_score"] += float(r.get("total_score") or 0)

        term = str(r.get("termination_reason") or "unknown")
        termination_map[term] = termination_map.get(term, 0) + 1

        vlist = list(r.get("violations") or [])
        if vlist:
            cases_with_violations += 1
        total_violations += len(vlist)
        pe["violations"] += len(vlist)

        for v in vlist:
            cid = str(v.get("constraint_id") or v.get("constraint_ref") or "?")
            re = rule_map.setdefault(
                cid,
                {
                    "constraint_id": cid,
                    "count": 0,
                    "totalDeduction": 0.0,
                    "text": v.get("constraint_text") or "",
                    "violation_type": v.get("violation_type") or "",
                    "description": _enrich_rule_description(
                        cid, v.get("constraint_text") or "", v.get("violation_type") or ""
                    ),
                },
            )
            re["count"] += 1
            re["totalDeduction"] += float(v.get("deduction") or 0)
            if not re.get("text") and v.get("constraint_text"):
                re["text"] = v.get("constraint_text")
            if not re.get("violation_type") and v.get("violation_type"):
                re["violation_type"] = v.get("violation_type")
            re["description"] = _enrich_rule_description(
                cid, re.get("text") or "", re.get("violation_type") or ""
            )
            vt = str(v.get("violation_type") or "other")
            type_map[vt] = type_map.get(vt, 0) + 1

    persona_stats = []
    for p in persona_map.values():
        c = max(1, int(p["count"]))
        persona_stats.append(
            {
                **p,
                "avgScore": round(p["total_score"] / c, 1),
            }
        )
    persona_stats.sort(key=lambda x: x["avgScore"], reverse=True)

    return {
        "ruleFailures": sorted(rule_map.values(), key=lambda x: x["count"], reverse=True),
        "violationTypes": [{"type": k, "count": v} for k, v in sorted(type_map.items(), key=lambda x: -x[1])],
        "personaStats": persona_stats,
        "terminationStats": [
            {
                "reason": k,
                "count": v,
                "label": {
                    "goal_achieved": "目标达成",
                    "max_turns": "轮次上限",
                    "user_refused": "用户拒绝",
                    "hangup": "挂断",
                    "hard_violation": "硬边界违规",
                    "runner_error": "运行错误",
                    "plan_timeout": "计划超时",
                }.get(k, k),
            }
            for k, v in sorted(termination_map.items(), key=lambda x: -x[1])
        ],
        "totalViolations": total_violations,
        "casesWithViolations": cases_with_violations,
    }
