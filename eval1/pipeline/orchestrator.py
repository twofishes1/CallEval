"""Eval1 full pipeline: Layer1 analysis + Layer2/3 evaluation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from eval1.analysis_service import build_layer1_analysis
from eval1.pipeline.runner import EvalRunner
from eval1.report.analytics import build_scoring_analytics
from eval1.report.test_report import build_eval_test_report


def _dimension_averages_from_reports(reports: List[Dict[str, Any]]) -> Dict[str, float]:
    dim_acc: Dict[str, List[float]] = {}
    for r in reports:
        for k, v in (r.get("dimension_scores") or {}).items():
            dim_acc.setdefault(str(k), []).append(float(v))
    return {k: round(sum(vals) / max(1, len(vals)), 1) for k, vals in dim_acc.items()}


def _grade_distribution(reports: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for r in reports:
        g = str(r.get("grade") or "?")
        dist[g] = dist.get(g, 0) + 1
    return dist


def enrich_eval_payload(payload: Dict[str, Any], *, layer1: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Shape runner output for Eval1 Studio (Layer2/3 views)."""
    reports = list(payload.get("reports") or [])
    dataset_id = str(payload.get("dataset_id") or "")
    grade_dist = _grade_distribution(reports)
    dimension_averages = _dimension_averages_from_reports(reports)
    analytics = build_scoring_analytics(reports)
    test_report = build_eval_test_report(
        summary={
            "count": payload.get("count", len(reports)),
            "average_score": payload.get("average_score", 0.0),
            "grade_distribution": grade_dist,
            "dimension_averages": dimension_averages,
        },
        meta=payload.get("meta") or {},
        reports=reports,
        dataset_id=dataset_id,
        layer1_summary=payload.get("layer1_summary") or (layer1 or {}).get("summary"),
    )

    layer2 = dict(payload.get("layer2") or {})
    if layer1 and not layer2.get("paths_by_id"):
        paths_by_id = {
            p["path_id"]: p
            for p in (layer1.get("paths") or [])
            if isinstance(p, dict) and p.get("path_id")
        }
        if paths_by_id:
            layer2 = {**layer2, "paths_by_id": paths_by_id}

    meta = payload.get("meta") or {}
    return {
        "dataset_id": dataset_id,
        "source": "eval1_pipeline",
        "phase": "complete",
        "bot_provider": str(meta.get("bot_provider") or "qwen"),
        "bot_model": str(meta.get("bot_model") or meta.get("llm_model_main") or ""),
        "layer1": layer1,
        "reports": reports,
        "layer2": layer2,
        "health": payload.get("health"),
        "summary": {
            "count": payload.get("count", len(reports)),
            "average_score": payload.get("average_score", 0.0),
            "grade_distribution": grade_dist,
            "dimension_averages": dimension_averages,
            "meta": payload.get("meta") or {},
            "analytics": analytics,
            "test_report": test_report,
        },
    }


async def run_eval1_pipeline(
    dataset_id: str,
    *,
    max_plans: int = 12,
    max_concurrent_dialogues: int = 2,
    plan_timeout_sec: float = 900.0,
    fast_mode: bool = False,
    skip_llm_judge: bool = False,
    layer1_only: bool = False,
    include_control_group: bool = False,
    bot_provider: str = "qwen",
    plan_ids: List[str] | None = None,
    resume: bool = True,
) -> Dict[str, Any]:
    layer1 = await build_layer1_analysis(dataset_id)
    if layer1_only:
        return {
            "dataset_id": dataset_id,
            "source": "eval1_pipeline",
            "phase": "layer1",
            "layer1": layer1,
            "layer1_summary": layer1.get("summary"),
        }

    payload = await EvalRunner().run(
        dataset_id=dataset_id,
        max_plans=max_plans,
        max_concurrent_dialogues=max_concurrent_dialogues,
        plan_timeout_sec=plan_timeout_sec,
        fast_mode=fast_mode,
        skip_llm_judge=skip_llm_judge,
        show_progress=False,
        include_control_group=include_control_group,
        bot_provider=bot_provider,
        plan_ids=plan_ids,
        resume=resume,
    )
    return enrich_eval_payload(payload, layer1=layer1)
