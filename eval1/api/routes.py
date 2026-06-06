from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from eval1.analysis_service import build_layer1_analysis, list_eval1_datasets
from eval1.api.schemas import Eval1AnalysisResponse, Eval1DatasetSummary, HealthResponse
from eval1.bot_provider import (
    list_available_report_providers,
    normalize_bot_provider,
    reports_output_path,
)
from eval1.data_ingest import ingest_upload
from eval1.pipeline.orchestrator import enrich_eval_payload, run_eval1_pipeline
from eval1.pipeline.runner import EvalRunner

router = APIRouter()
_EVAL1_ROOT = Path(__file__).resolve().parents[1]


def _load_cached_reports(dataset_id: str, bot_provider: str) -> Dict[str, Any] | None:
    out = reports_output_path(dataset_id, bot_provider)
    if not out.exists():
        return None
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


async def _load_or_run_reports(
    dataset_id: str,
    *,
    bot_provider: str,
    refresh: bool,
    max_plans: int,
    concurrency: int,
    plan_timeout_sec: float,
    fast: bool,
    include_control_group: bool,
) -> Dict[str, Any]:
    provider = normalize_bot_provider(bot_provider)
    report_path = reports_output_path(dataset_id, provider)

    if refresh:
        try:
            payload = await EvalRunner().run(
                dataset_id=dataset_id,
                max_plans=max_plans,
                max_concurrent_dialogues=concurrency,
                plan_timeout_sec=plan_timeout_sec,
                fast_mode=fast,
                show_progress=False,
                include_control_group=include_control_group,
                bot_provider=provider,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
    else:
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
    """List which bot-provider report files exist for a dataset."""
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


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Upload xlsx/json/txt into eval1/data/uploads and register datasets."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        return ingest_upload(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/pipeline/{dataset_id}/run")
async def run_pipeline(
    dataset_id: str,
    max_plans: int = Query(
        0,
        ge=0,
        le=120,
        description="0=跑全部语义匹配计划；>0 仅用于 smoke 截断",
    ),
    concurrency: int = Query(2, ge=1, le=8),
    plan_timeout_sec: float = Query(900.0, ge=60.0, le=3600.0),
    fast: bool = Query(False, description="true=降为 qwen-turbo 快速模式；默认 false 使用 qwen-plus"),
    layer1_only: bool = Query(False),
    include_control_group: bool = Query(
        False,
        description="已废弃：全量路径×角色笛卡尔积，矛盾组合仅 plan_group 标注",
    ),
    bot_provider: str = Query(
        "qwen",
        description="被测 Bot：qwen | deepseek（报告写入不同 JSON 文件）",
    ),
    plan_id: List[str] | None = Query(
        None,
        description="部分重跑：仅执行匹配的 plan（如 P36:impatient），其余复用已有报告",
    ),
    scenario: str | None = Query(
        None,
        description="部分重跑：仅执行探针场景路径，如 D10 / D9",
    ),
):
    """Layer1 parse → path enum → Layer2 dialogue → Layer3 scoring (full Eval1)."""
    plan_ids: List[str] = list(plan_id or [])
    if scenario:
        tag = str(scenario).strip().upper()
        plan_ids.append(f"@{tag}" if tag in {"D10", "D9"} else tag)
    try:
        return await run_eval1_pipeline(
            dataset_id,
            max_plans=max_plans,
            max_concurrent_dialogues=concurrency,
            plan_timeout_sec=plan_timeout_sec,
            fast_mode=fast,
            layer1_only=layer1_only,
            include_control_group=include_control_group,
            bot_provider=bot_provider,
            plan_ids=plan_ids or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/upload-and-run")
async def upload_and_run(
    file: UploadFile = File(...),
    dataset_index: int = Query(0, ge=0),
    max_plans: int = Query(
        0,
        ge=0,
        le=120,
        description="0=跑全部语义匹配计划；>0 仅用于 smoke 截断",
    ),
    concurrency: int = Query(2, ge=1, le=8),
    plan_timeout_sec: float = Query(900.0, ge=60.0, le=3600.0),
    fast: bool = Query(False, description="true=降为 qwen-turbo 快速模式；默认 false 使用 qwen-plus"),
    include_control_group: bool = Query(False),
    bot_provider: str = Query("qwen", description="被测 Bot：qwen | deepseek"),
):
    """Upload data file then run full Eval1 pipeline on one dataset (default: first row)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        ingested = ingest_upload(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    rows = ingested.get("datasets") or []
    if not rows:
        raise HTTPException(status_code=400, detail="未解析到数据集")
    idx = min(dataset_index, len(rows) - 1)
    dataset_id = rows[idx]["dataset_id"]
    try:
        run_result = await run_eval1_pipeline(
            dataset_id,
            max_plans=max_plans,
            max_concurrent_dialogues=concurrency,
            plan_timeout_sec=plan_timeout_sec,
            fast_mode=fast,
            include_control_group=include_control_group,
            bot_provider=bot_provider,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"upload": ingested, "dataset_id": dataset_id, "pipeline": run_result}


@router.get("/layer2/{dataset_id}")
async def layer2_dialogues(
    dataset_id: str,
    max_plans: int = Query(
        0,
        ge=0,
        le=120,
        description="0=不截断；>0 仅在 refresh=true 重跑时生效",
    ),
    refresh: bool = Query(False),
    concurrency: int = Query(2, ge=1, le=8),
    num_judges: int = Query(1, ge=1, le=5),
    plan_timeout_sec: float = Query(900.0, ge=60.0, le=3600.0),
    fast: bool = Query(False, description="true=降为 qwen-turbo 快速模式；默认 false 使用 qwen-plus"),
    include_control_group: bool = Query(False),
    bot_provider: str = Query("qwen", description="读取/生成哪份 Bot 评测报告：qwen | deepseek"),
):
    """Load cached eval report or run Layer2–3; shape payload for Eval Studio."""
    _ = num_judges  # reserved for multi-judge runs
    return await _load_or_run_reports(
        dataset_id,
        bot_provider=bot_provider,
        refresh=refresh,
        max_plans=max_plans,
        concurrency=concurrency,
        plan_timeout_sec=plan_timeout_sec,
        fast=fast,
        include_control_group=include_control_group,
    )
