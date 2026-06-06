"""Read-only Eval1 API routes — lightweight, no langgraph import."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from eval1.analysis_service import build_layer1_analysis, list_eval1_datasets
from eval1.api.schemas import Eval1AnalysisResponse, Eval1DatasetSummary, HealthResponse
from eval1.bot_provider import (
    list_available_report_providers,
    normalize_bot_provider,
    reports_output_path,
)
from eval1.payload_enrich import enrich_eval_payload

router = APIRouter()


def _load_cached_reports(dataset_id: str, bot_provider: str) -> Dict[str, Any] | None:
    out = reports_output_path(dataset_id, bot_provider)
    if not out.exists():
        return None
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


async def _load_cached_report_view(
    dataset_id: str,
    *,
    bot_provider: str,
) -> Dict[str, Any]:
    provider = normalize_bot_provider(bot_provider)
    report_path = reports_output_path(dataset_id, provider)
    payload = _load_cached_reports(dataset_id, provider)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"未找到 {provider} 评测报告（{report_path.name}）。"
                f"请先 CLI/API 跑评测，或在前端点「重新评测」。"
            ),
        )
    layer1 = None
    try:
        layer1 = await build_layer1_analysis(dataset_id)
    except ValueError:
        layer1 = None
    enriched = enrich_eval_payload(payload, layer1=layer1)
    enriched["bot_provider"] = provider
    enriched["report_file"] = report_path.name
    return enriched


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(ok=True)


@router.get("/datasets", response_model=List[Eval1DatasetSummary])
def datasets() -> List[Eval1DatasetSummary]:
    return [Eval1DatasetSummary(**x) for x in list_eval1_datasets()]


@router.get("/reports/{dataset_id}/providers")
def report_providers(dataset_id: str):
    return {
        "dataset_id": dataset_id,
        "providers": list_available_report_providers(dataset_id),
    }


@router.get("/layer1/{dataset_id}", response_model=Eval1AnalysisResponse)
async def layer1_analysis(dataset_id: str) -> Eval1AnalysisResponse:
    try:
        data = await build_layer1_analysis(dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return Eval1AnalysisResponse(**data)


@router.get("/layer2/{dataset_id}")
async def layer2_dialogues(
    dataset_id: str,
    max_plans: int = Query(0, ge=0, le=120),
    refresh: bool = Query(False),
    concurrency: int = Query(2, ge=1, le=8),
    num_judges: int = Query(1, ge=1, le=5),
    plan_timeout_sec: float = Query(900.0, ge=60.0, le=3600.0),
    fast: bool = Query(False),
    include_control_group: bool = Query(False),
    bot_provider: str = Query("qwen"),
):
    _ = num_judges
    if refresh:
        from eval1.api.write_routes import run_layer2_refresh

        return await run_layer2_refresh(
            dataset_id,
            bot_provider=bot_provider,
            max_plans=max_plans,
            concurrency=concurrency,
            plan_timeout_sec=plan_timeout_sec,
            fast=fast,
            include_control_group=include_control_group,
        )
    return await _load_cached_report_view(dataset_id, bot_provider=bot_provider)
