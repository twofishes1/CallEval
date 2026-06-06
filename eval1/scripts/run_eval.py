from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval1.bot_provider import reports_output_path
from eval1.pipeline.runner import EvalRunner


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run eval1 end-to-end evaluation.")
    parser.add_argument("--dataset-id", type=str, default=None)
    parser.add_argument(
        "--max-plans",
        type=int,
        default=None,
        help="Cap plans for smoke/debug only. Omit or 0 = auto full coverage (paths x personas).",
    )
    parser.add_argument("--output-file", type=str, default=None)
    parser.add_argument("--concurrency", type=int, default=None, help="Parallel plans to run.")
    parser.add_argument(
        "--plan-timeout-sec",
        type=float,
        default=None,
        help="Per-plan timeout seconds (default from eval1 config, currently 900).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        default=False,
        help="Fast mode: downgrade to qwen-turbo for smoke/debug (default: off, use qwen-plus).",
    )
    parser.add_argument(
        "--no-fast",
        action="store_false",
        dest="fast",
        help="Use config models (default: qwen-plus for bot + user sim).",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Skip LLM judge (rule score only); fastest for debugging dialogues.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print per-plan progress in real time.",
    )
    parser.add_argument(
        "--include-control-group",
        action="store_true",
        help="Deprecated (ignored): full cartesian run; contradictions are annotated only.",
    )
    parser.add_argument(
        "--bot-provider",
        choices=["qwen", "deepseek"],
        default="qwen",
        help="Bot under test: qwen (default) or deepseek; writes separate JSON report files.",
    )
    parser.add_argument(
        "--plan-id",
        action="append",
        dest="plan_ids",
        default=None,
        help="Run only matching plan(s), e.g. P36:impatient or P36 (repeatable).",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Run probe scenario paths only, e.g. D10 or D9.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Same as --fresh: ignore checkpoint and re-run all selected plans.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Full re-run from scratch; existing report is backed up to outputs/backups/ first.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show checkpoint progress and exit (no LLM calls).",
    )
    return parser


async def _run_async(args: argparse.Namespace):
    fresh = bool(args.fresh or args.no_resume)
    if args.status:
        from eval1.analysis_service import build_layer1_analysis, list_eval1_datasets
        from eval1.layer1.models import EnumeratedPath
        from eval1.pipeline.planner import ExecutionPlanner, select_execution_plans
        from eval1.pipeline.report_merge import completed_plan_ids, load_existing_report, report_plan_count

        dataset_id = args.dataset_id
        if not dataset_id:
            ds = list_eval1_datasets()
            dataset_id = ds[0]["dataset_id"] if ds else "instruction_2"
        out = Path(args.output_file) if args.output_file else reports_output_path(
            str(dataset_id), args.bot_provider
        )
        existing = load_existing_report(out)
        layer1 = await build_layer1_analysis(str(dataset_id))
        paths = [EnumeratedPath.model_validate(p) for p in (layer1.get("paths") or [])]
        all_plans, _ = ExecutionPlanner().plan(paths, {})
        plans, _ = select_execution_plans(all_plans, args.max_plans)
        done = completed_plan_ids(existing)
        total = len(plans)
        n = report_plan_count(existing)
        print(f"dataset={dataset_id} bot={args.bot_provider} file={out.name}")
        print(f"progress: {n}/{total} done, {max(0, total - n)} remaining")
        if existing:
            meta = existing.get("meta") or {}
            print(f"bot_model={meta.get('bot_model', '?')} avg={existing.get('average_score', '?')}")
        else:
            print("no report file yet")
        return {"dataset_id": dataset_id, "count": n, "status_only": True}

    plan_ids = list(args.plan_ids or [])
    if args.scenario:
        tag = str(args.scenario).strip().upper()
        if tag in {"D10", "D9"}:
            plan_ids.append(f"@{tag}")
        else:
            plan_ids.append(tag)
    if fresh and not plan_ids and args.progress:
        print(
            "[eval1] --fresh 全量重跑：忽略断点、跑完全部 plan；"
            "原报告会先备份到 eval1/outputs/backups/",
            flush=True,
        )
    runner = EvalRunner()
    return await runner.run(
        dataset_id=args.dataset_id,
        max_plans=args.max_plans,
        output_file=args.output_file,
        show_progress=args.progress,
        max_concurrent_dialogues=args.concurrency,
        plan_timeout_sec=args.plan_timeout_sec,
        fast_mode=bool(args.fast),
        skip_llm_judge=bool(args.skip_judge),
        include_control_group=bool(args.include_control_group),
        bot_provider=args.bot_provider,
        plan_ids=plan_ids or None,
        resume=not fresh,
    )


def main() -> None:
    args = _build_parser().parse_args()
    payload = asyncio.run(_run_async(args))
    if payload.get("status_only"):
        return
    meta = payload.get("meta") or {}
    out_path = reports_output_path(
        payload["dataset_id"],
        meta.get("bot_provider", args.bot_provider),
    )
    print(
        f"eval1 done: dataset={payload['dataset_id']} "
        f"bot={meta.get('bot_provider', args.bot_provider)} "
        f"model={meta.get('bot_model', '?')} "
        f"out={out_path.name} "
        f"reports={payload['count']}/{meta.get('plans_total', payload['count'])} "
        f"avg={payload['average_score']} "
        f"coverage={meta.get('coverage_mode', 'unknown')}"
        + (
            f" rerun={meta.get('plans_rerun', 0)} reused={meta.get('plans_reused', 0)}"
            if meta.get("partial_rerun")
            else (
                f" resumed={meta.get('plans_resumed', 0)}"
                if meta.get("resume_mode")
                else ""
            )
        )
    )


if __name__ == "__main__":
    main()
