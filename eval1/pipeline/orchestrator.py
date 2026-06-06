"""Eval1 full pipeline: Layer1 analysis + Layer2/3 evaluation."""

from __future__ import annotations

from typing import Any, Dict, List

from eval1.analysis_service import build_layer1_analysis
from eval1.payload_enrich import enrich_eval_payload
from eval1.pipeline.runner import EvalRunner


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
