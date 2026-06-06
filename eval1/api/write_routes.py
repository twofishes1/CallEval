"""Write / pipeline Eval1 API routes — heavy imports (langgraph, EvalRunner)."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from eval1.analysis_service import build_layer1_analysis
from eval1.bot_provider import normalize_bot_provider, reports_output_path
from eval1.data_ingest import ingest_upload
from eval1.payload_enrich import enrich_eval_payload
from eval1.pipeline.orchestrator import run_eval1_pipeline
from eval1.pipeline.runner import EvalRunner

router = APIRouter()


async def run_layer2_refresh(
    dataset_id: str,
    *,
    bot_provider: str,
    max_plans: int,
    concurrency: int,
    plan_timeout_sec: float,
    fast: bool,
    include_control_group: bool,
) -> Dict[str, Any]:
    provider = normalize_bot_provider(bot_provider)
    report_path = reports_output_path(dataset_id, provider)
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
    layer1 = None
    try:
        layer1 = await build_layer1_analysis(dataset_id)
    except ValueError:
        layer1 = None
    enriched = enrich_eval_payload(payload, layer1=layer1)
    enriched["bot_provider"] = provider
    enriched["report_file"] = report_path.name
    return enriched


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
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
    max_plans: int = Query(0, ge=0, le=120),
    concurrency: int = Query(2, ge=1, le=8),
    plan_timeout_sec: float = Query(900.0, ge=60.0, le=3600.0),
    fast: bool = Query(False),
    layer1_only: bool = Query(False),
    include_control_group: bool = Query(False),
    bot_provider: str = Query("qwen"),
    plan_id: List[str] | None = Query(None),
    scenario: str | None = Query(None),
):
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
    max_plans: int = Query(0, ge=0, le=120),
    concurrency: int = Query(2, ge=1, le=8),
    plan_timeout_sec: float = Query(900.0, ge=60.0, le=3600.0),
    fast: bool = Query(False),
    include_control_group: bool = Query(False),
    bot_provider: str = Query("qwen"),
):
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
