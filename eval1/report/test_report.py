"""Structured eval test report document (mirrors frontend buildEvalTestReport.js)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

from eval1.report.analytics import PERSONA_LABELS, _enrich_rule_description, build_scoring_analytics

DIM_LABELS = {
    "flow_adherence": "流程遵循",
    "dialogue_compliance": "话术合规",
    "knowledge_accuracy": "知识准确",
    "retention_effectiveness": "挽留效果",
    "boundary_handling": "边界处理",
    "naturalness": "自然度",
}

TERMINATION_LABELS = {
    "goal_achieved": "目标达成",
    "max_turns": "轮次上限",
    "user_refused": "用户拒绝",
    "hangup": "挂断",
    "hard_violation": "硬边界违规",
    "runner_error": "运行错误",
    "plan_timeout": "计划超时",
}


def _overall_verdict(avg: float) -> Dict[str, str]:
    if avg >= 90:
        return {
            "level": "优秀",
            "summary": "模型在复杂指令场景下整体表现优秀，多数用例达到 A 级，可进入小范围灰度或定向优化阶段。",
        }
    if avg >= 80:
        return {
            "level": "良好",
            "summary": "模型整体达到良好水平，主流程与话术基本可靠，但仍有可优化的维度与规则合规问题。",
        }
    if avg >= 70:
        return {
            "level": "合格",
            "summary": "模型达到基本可用标准，建议在关键薄弱维度与高频违规项上优先整改后再扩大覆盖。",
        }
    if avg >= 60:
        return {
            "level": "待改进",
            "summary": "模型尚未稳定达标，存在较多流程、话术或知识类问题，需针对性迭代与复测。",
        }
    return {
        "level": "不达标",
        "summary": "模型当前综合表现未达上线要求，建议暂停放量，按主要发现逐项修复后重新全量评测。",
    }


def _pct(part: int, total: int) -> float:
    if not total:
        return 0.0
    return round(part / total * 1000) / 10


def build_eval_test_report(
    *,
    summary: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    reports: Optional[List[Dict[str, Any]]] = None,
    dataset_name: Optional[str] = None,
    dataset_id: Optional[str] = None,
    layer1_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Agent-style document synthesis from scored case records (no LLM required)."""
    summary = summary or {}
    meta = meta or {}
    reports = list(reports or [])
    analytics = build_scoring_analytics(reports)

    count = int(summary.get("count") or len(reports))
    avg = float(summary.get("average_score") or 0.0)
    grades = dict(summary.get("grade_distribution") or {})
    dim_avg = dict(summary.get("dimension_averages") or {})
    verdict = _overall_verdict(avg)

    weight_rule = str(meta.get("weight_rule") or "0.4")
    weight_llm = str(meta.get("weight_llm") or "0.6")
    model_name = str(meta.get("model_name") or meta.get("model") or "被测对话模型")
    report_date = date.today().strftime("%Y年%m月%d日")

    pass_count = int(grades.get("A", 0)) + int(grades.get("B", 0))
    fail_count = int(grades.get("D", 0)) + int(grades.get("F", 0))
    violation_cases = int(analytics.get("casesWithViolations") or 0)
    total_violations = int(analytics.get("totalViolations") or 0)

    dim_sorted = sorted(dim_avg.items(), key=lambda x: x[1], reverse=True)
    top_dim = dim_sorted[0] if dim_sorted else None
    low_dim = dim_sorted[-1] if dim_sorted else None

    persona_stats = list(analytics.get("personaStats") or [])
    path_stats = list(analytics.get("pathStats") or [])
    best_persona = persona_stats[0] if persona_stats else None
    worst_persona = persona_stats[-1] if persona_stats else None
    rule_failures = list(analytics.get("ruleFailures") or [])[:12]
    violation_types = list(analytics.get("violationTypes") or [])
    term_stats = list(analytics.get("terminationStats") or [])
    score_summary = dict(analytics.get("scoreSummary") or {})
    plan_group_stats = list(analytics.get("planGroupStats") or [])
    for t in term_stats:
        if not t.get("label") or t.get("label") == t.get("reason"):
            t["label"] = TERMINATION_LABELS.get(str(t.get("reason")), str(t.get("reason")))

    findings: List[Dict[str, str]] = []
    if count > 0:
        findings.append(
            {
                "title": "综合得分与等级分布",
                "body": (
                    f"共执行 {count} 个测试用例，加权综合均分 {avg:.1f} 分，综合评定为「{verdict['level']}」。"
                    f"其中 A/B 级 {pass_count} 例（{_pct(pass_count, count)}%），"
                    f"D/F 级 {fail_count} 例（{_pct(fail_count, count)}%）。"
                    f"计分采用规则分×{weight_rule} + LLM 评委分×{weight_llm}。"
                ),
            }
        )
    if low_dim:
        top_score = float(top_dim[1]) if top_dim else 0.0
        top_name = DIM_LABELS.get(top_dim[0], top_dim[0]) if top_dim else "—"
        findings.append(
            {
                "title": "能力维度短板",
                "body": (
                    f"六维评测中，「{DIM_LABELS.get(low_dim[0], low_dim[0])}」均分最低（{float(low_dim[1]):.1f}），"
                    f"「{top_name}」相对最高（{top_score:.1f}）。"
                    "建议优先针对低分维度对应的 Rubric 条目做话术与流程补强。"
                ),
            }
        )
    if violation_cases > 0:
        rule_lines = "；".join(
            f"「{r['constraint_id']}」{r.get('description', '')}（触发 {r['count']} 次，"
            f"累计扣分 {round(float(r.get('totalDeduction') or 0), 1)}）"
            for r in rule_failures
        )
        findings.append(
            {
                "title": "规则合规与硬约束",
                "body": (
                    f"{violation_cases} 个用例出现规则违规，合计 {total_violations} 次。"
                    f"高频项：{rule_lines or '见统计图表'}。"
                ),
            }
        )
    else:
        findings.append(
            {
                "title": "规则合规与硬约束",
                "body": "本轮测试未记录到规则引擎扣分项，规则分均为满分；仍需结合 LLM 维度分审视流程与表达质量。",
            }
        )
    if len(persona_stats) >= 2 and best_persona and worst_persona:
        gap = round(float(best_persona["avgScore"]) - float(worst_persona["avgScore"]), 1)
        findings.append(
            {
                "title": "用户角色差异",
                "body": (
                    f"在不同用户画像下，{best_persona['label']} 均分最高（{best_persona['avgScore']}），"
                    f"{worst_persona['label']} 最低（{worst_persona['avgScore']}），分差约 {gap} 分。"
                    f"模型对{worst_persona['label']}场景的应对能力需重点验证。"
                ),
            }
        )
    if term_stats:
        top_term = term_stats[0]
        extra = ""
        if len(term_stats) > 1:
            extra = "其余包括 " + "、".join(
                f"{t['label']} {t['count']} 例" for t in term_stats[1:3]
            ) + " 等。"
        findings.append(
            {
                "title": "对话终止情况",
                "body": (
                    f"对话终止以「{top_term['label']}」为主（{top_term['count']} 例，"
                    f"占比 {_pct(int(top_term['count']), count)}%）。{extra}"
                ),
            }
        )

    imp_freq: Dict[str, int] = {}
    for r in reports:
        items: List[str] = []
        if r.get("top_improvement"):
            items.append(str(r["top_improvement"]).strip())
        for s in r.get("improvement_suggestions") or []:
            t = str(s or "").strip()
            if t:
                items.append(t)
        for t in items:
            if len(t) < 4:
                continue
            imp_freq[t] = imp_freq.get(t, 0) + 1
    improvements = sorted(imp_freq.items(), key=lambda x: -x[1])[:6]

    recommendations: List[str] = []
    if fail_count > 0:
        recommendations.append(f"对 {fail_count} 个 D/F 级用例做人工复盘，对照路径设计与 Judge 证据链定位根因。")
    if low_dim and float(low_dim[1]) < 75:
        recommendations.append(
            f"围绕「{DIM_LABELS.get(low_dim[0], low_dim[0])}」补充训练样本或 Prompt 约束，"
            "并在 Layer2 对话中增加该维度的抽检。"
        )
    for r in rule_failures[:3]:
        recommendations.append(
            f"治理规则 {r['constraint_id']}："
            f"{_enrich_rule_description(r['constraint_id'], r.get('text', ''), r.get('violation_type', ''))}"
        )
    for text, n in improvements[:4]:
        recommendations.append(f"（{n} 例提及）{text}" if n > 1 else text)
    if not recommendations:
        recommendations.append("维持当前策略，定期复测并跟踪维度均分与违规率变化。")

    weak = sorted(
        [
            r
            for r in reports
            if str(r.get("grade")) in {"D", "F"} or float(r.get("total_score") or 0) < 70
        ],
        key=lambda x: float(x.get("total_score") or 0),
    )[:8]
    weak_cases = [
        {
            "path_id": r.get("path_id"),
            "persona": PERSONA_LABELS.get(str(r.get("persona_type")), str(r.get("persona_type"))),
            "score": f"{float(r.get('total_score') or 0):.1f}",
            "grade": r.get("grade"),
            "top_issue": r.get("top_improvement")
            or ((r.get("violations") or [{}])[0].get("constraint_text") if r.get("violations") else None)
            or "—",
        }
        for r in weak
    ]

    path_count = None
    if layer1_summary:
        path_count = layer1_summary.get("path_count")
        if path_count is None and isinstance(layer1_summary.get("paths"), int):
            path_count = layer1_summary["paths"]

    ds_label = dataset_name or dataset_id or "Eval1 测试集"
    return {
        "header": {
            "title": "CallEval 复杂指令对话模型评测报告",
            "subtitle": ds_label,
            "reportDate": report_date,
            "modelName": model_name,
            "datasetId": dataset_id or "—",
            "caseCount": count,
            "pathCount": path_count,
        },
        "verdict": verdict,
        "executiveSummary": [
            f"本次对「{model_name}」在「{ds_label}」上完成 {count} 条复杂指令对话测试。"
            f"综合均分 {avg:.1f}，评定等级：{verdict['level']}。",
            verdict["summary"],
            (
                f"{_pct(violation_cases, count)}% 的用例触发规则扣分（共 {total_violations} 次违规记录），"
                "需与 LLM 维度评分一并纳入上线决策。"
                if violation_cases > 0
                else "规则引擎未记录扣分，上线评估可主要依据 LLM 六维能力与等级分布。"
            ),
        ],
        "testOverview": {
            "scope": (
                f"覆盖 {count} 条测试用例"
                + (f"，对应 Layer1 路径规划 {path_count} 条" if path_count is not None else "")
                + "，含多用户角色与多业务路径。"
                if count
                else "暂无用例数据。"
            ),
            "method": (
                "采用 Eval1 三层评测：Layer1 知识图谱与路径规划 → "
                "Layer2 多角色对话仿真 → Layer3 规则分 + LLM Rubric 六维评分。"
            ),
            "scoring": f"总分 = 规则分 × {weight_rule} + LLM 分 × {weight_llm}，等级按总分区间映射 A–F。",
        },
        "gradeRows": [
            {"grade": g, "count": int(n), "percent": _pct(int(n), count)}
            for g, n in sorted(grades.items())
        ],
        "dimensionRows": [
            {"dimension": DIM_LABELS.get(k, k), "score": round(float(v), 1)} for k, v in dim_sorted
        ],
        "scoreSummary": {
            "avgTotal": round(avg, 1) if count else None,
            "avgRule": score_summary.get("avgRule"),
            "avgLlm": score_summary.get("avgLlm"),
            "avgFlowAdherence": score_summary.get("avgFlowAdherence"),
        },
        "personaRows": [
            {
                "persona": p.get("label"),
                "count": p.get("count"),
                "avgScore": p.get("avgScore"),
                "avgRule": p.get("avgRule"),
                "avgLlm": p.get("avgLlm"),
                "violations": p.get("violations"),
            }
            for p in persona_stats
        ],
        "pathRows": [
            {
                "path_id": p.get("path_id"),
                "count": p.get("count"),
                "avgScore": p.get("avgScore"),
                "violations": p.get("violations"),
            }
            for p in path_stats
        ],
        "ruleFailureRows": [
            {
                "id": r.get("constraint_id"),
                "description": r.get("description")
                or _enrich_rule_description(
                    r.get("constraint_id", ""),
                    r.get("text", ""),
                    r.get("violation_type", ""),
                ),
                "count": r.get("count"),
                "deduction": round(float(r.get("totalDeduction") or 0), 1),
                "type": r.get("violation_type") or "—",
            }
            for r in rule_failures
        ],
        "violationTypeRows": [
            {
                "type": v.get("label"),
                "count": v.get("count"),
                "percent": _pct(int(v.get("count") or 0), total_violations),
            }
            for v in violation_types
        ],
        "terminationRows": [
            {
                "reason": t.get("label"),
                "count": t.get("count"),
                "percent": _pct(int(t.get("count") or 0), count),
            }
            for t in term_stats
        ],
        "planGroupRows": [
            {
                "group": g.get("label"),
                "count": g.get("count"),
                "avgScore": g.get("avgScore"),
                "avgRule": g.get("avgRule"),
                "avgLlm": g.get("avgLlm"),
                "avgFlow": f"{g.get('avgFlow')}%" if g.get("avgFlow") is not None else "—",
                "violations": g.get("violations"),
                "failCount": g.get("failCount"),
            }
            for g in plan_group_stats
        ],
        "findings": findings,
        "conclusions": [
            c
            for c in [
                f"综合结论：模型本轮评测结果为「{verdict['level']}」（均分 {avg:.1f}）。",
                (
                    f"存在 {fail_count} 个低等级用例，不建议在未修复前全量发布。"
                    if fail_count > 0
                    else "低等级用例占比较低，可在修复已知违规项后安排回归测试。"
                ),
                (
                    f"角色维度上需关注 {worst_persona['label']} 场景；"
                    "规则与流程类问题请对照 Layer2 对话与违规明细。"
                    if worst_persona and best_persona
                    else None
                ),
            ]
            if c
        ],
        "recommendations": list(dict.fromkeys(recommendations)),
        "weakCases": weak_cases,
        "meta": {
            "generator": "eval1.report.test_report",
            "version": "1.0",
            "source": "backend_aggregate",
        },
    }
