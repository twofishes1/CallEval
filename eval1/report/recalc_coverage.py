"""Recompute path coverage / flow_miss from saved Layer2 dialogues (no re-simulation)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from eval1.layer2.goal_fsm import FLOW_COVERAGE_VIOLATION_THRESHOLD, GoalFSM
from eval1.layer3.aggregator import Aggregator
from eval1.layer3.rule_judge import RuleJudge
from eval1.layer3.scoring_config import ScoringConfig
from eval1.pipeline.runner import _attach_flow_miss_violation


@dataclass
class _SimplePath:
    nodes: List[str]


@dataclass
class _SimplePlan:
    path: _SimplePath


def infer_covered_nodes(dialogue: Dict[str, Any]) -> List[str]:
    """Rebuild FSM visited steps from bot_state_log."""
    covered: List[str] = []
    for entry in dialogue.get("bot_state_log") or []:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("current_step_id") or "").strip()
        if sid and sid not in covered:
            covered.append(sid)
    return covered


def recalc_flow_adherence(dialogue: Dict[str, Any]) -> float:
    path_nodes = list(dialogue.get("path_nodes") or [])
    covered = infer_covered_nodes(dialogue)
    log = list((dialogue.get("bot_state") or {}).get("bot_action_log") or [])
    fsm = GoalFSM.from_path(path_nodes)
    return float(fsm.get_flow_adherence_rate(covered, bot_action_log=log))


def _runtime_violations(violations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [v for v in violations if str(v.get("violation_type") or "") != "flow_miss"]


def recalc_one(
    report: Dict[str, Any],
    dialogue: Dict[str, Any],
    *,
    weight_rule: float = 0.4,
    weight_llm: float = 0.6,
) -> Dict[str, Any]:
    """Return report fields patched with recalculated coverage + rule score."""
    merged = {**report, **{k: dialogue[k] for k in dialogue if k not in report}}
    new_flow = recalc_flow_adherence(dialogue)
    path_id = str(merged.get("path_id") or dialogue.get("path_id") or "?")

    dialogue_for_rule: Dict[str, Any] = {
        "violations": _runtime_violations(list(merged.get("violations") or [])),
        "flow_adherence_rate": new_flow,
        "hard_violation": bool(merged.get("hard_violation")),
        "repetitive_bot_count": int(merged.get("repetitive_bot_count") or 0),
        "opening_line_match": bool(merged.get("opening_line_match")),
        "bot_state": dict(merged.get("bot_state") or {}),
        "messages": list(merged.get("messages") or []),
    }
    _attach_flow_miss_violation(dialogue_for_rule, path_id)

    plan = _SimplePlan(path=_SimplePath(list(dialogue.get("path_nodes") or [])))
    rule_ret = RuleJudge().score(plan, dialogue_for_rule)

    llm_score = float(merged.get("llm_score") or 0)
    cfg = ScoringConfig(weight_rule=weight_rule, weight_llm=weight_llm)
    agg = Aggregator().aggregate(
        float(rule_ret["rule_score"]),
        llm_score,
        hard_fail=bool(rule_ret.get("hard_violation")),
        scoring=cfg,
    )

    violations: List[Dict[str, Any]] = list(dialogue_for_rule.get("violations") or [])
    for v in rule_ret.get("supplemental_violations") or []:
        if not isinstance(v, dict) or not v:
            continue
        if any(
            str(x.get("constraint_id")) == str(v.get("constraint_id"))
            and str(x.get("violation_type")) == str(v.get("violation_type"))
            for x in violations
        ):
            continue
        violations.append(v)

    out = dict(report)
    out.update(
        {
            "flow_adherence_rate": round(new_flow, 3),
            "flow_adherence_rate_legacy": merged.get("flow_adherence_rate"),
            "violations": violations,
            "rule_score": float(rule_ret["rule_score"]),
            "total_score": float(agg["total_score"]),
            "grade": str(agg["grade"]),
            "score_breakdown": str(agg.get("score_breakdown") or ""),
            "coverage_recalc_applied": True,
        }
    )
    return out


def recalc_eval_payload(
    payload: Dict[str, Any],
    *,
    weight_rule: Optional[float] = None,
    weight_llm: Optional[float] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Recalc all reports; return (new_payload, summary_delta)."""
    reports = list(payload.get("reports") or [])
    dialogues = {
        str(d.get("report_id")): d
        for d in (payload.get("layer2") or {}).get("dialogues") or []
        if d.get("report_id")
    }
    meta = (payload.get("summary") or {}).get("meta") or payload.get("meta") or {}
    wr = float(weight_rule if weight_rule is not None else meta.get("weight_rule") or 0.4)
    wl = float(weight_llm if weight_llm is not None else meta.get("weight_llm") or 0.6)

    old_flow_miss = 0
    new_flow_miss = 0
    recalc_reports: List[Dict[str, Any]] = []

    for r in reports:
        rid = str(r.get("report_id") or "")
        d = dialogues.get(rid)
        if not d or not d.get("path_nodes"):
            recalc_reports.append(r)
            continue
        if any(v.get("violation_type") == "flow_miss" for v in (r.get("violations") or [])):
            old_flow_miss += 1
        patched = recalc_one(r, d, weight_rule=wr, weight_llm=wl)
        if any(v.get("violation_type") == "flow_miss" for v in (patched.get("violations") or [])):
            new_flow_miss += 1
        recalc_reports.append(patched)

    new_payload = dict(payload)
    new_payload["reports"] = recalc_reports

    # Resummary
    count = len(recalc_reports)
    avg = sum(float(x.get("total_score") or 0) for x in recalc_reports) / count if count else 0
    grades: Dict[str, int] = {}
    dim_sum: Dict[str, float] = {}
    dim_n = 0
    for x in recalc_reports:
        g = str(x.get("grade") or "?")
        grades[g] = grades.get(g, 0) + 1
        ds = x.get("dimension_scores") or {}
        if ds:
            dim_n += 1
            for k, v in ds.items():
                dim_sum[k] = dim_sum.get(k, 0) + float(v)

    summary = dict(payload.get("summary") or {})
    summary["count"] = count
    summary["average_score"] = round(avg, 2)
    summary["grade_distribution"] = grades
    if dim_n:
        summary["dimension_averages"] = {
            k: round(v / dim_n, 2) for k, v in dim_sum.items()
        }
    summary["coverage_recalc"] = True
    new_payload["summary"] = summary

    delta = {
        "cases": count,
        "flow_miss_old": old_flow_miss,
        "flow_miss_new": new_flow_miss,
        "average_score_old": payload.get("summary", {}).get("average_score"),
        "average_score_new": round(avg, 2),
        "grade_distribution_new": grades,
    }
    return new_payload, delta
