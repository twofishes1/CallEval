from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Tuple

from eval1.analysis_service import build_layer1_analysis, list_eval1_datasets
from eval1.bot_provider import bot_provider_scope, get_bot_llm_profile, reports_output_path
from eval1.config import settings
from eval1.layer1.models import EnumeratedPath, EvalReport, ParsedInstruction, ViolationEvidence
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.goal_fsm import FLOW_COVERAGE_VIOLATION_THRESHOLD
from eval1.layer2.simulation_graph import SimulationGraph
from eval1.layer2.system_health import SystemHealthMetrics
from eval1.layer3.aggregator import Aggregator
from eval1.layer3.llm_judge import LLMJudge
from eval1.layer3.rule_judge import RuleJudge
from eval1.layer3.rubrics import DIMENSION_LABELS, DIMENSION_WEIGHTS
from eval1.layer3.scoring_config import ScoringConfig
from eval1.pipeline.planner import ExecutionPlanner, estimate_semantic_plan_total, select_execution_plans
from eval1.pipeline.report_merge import (
    ReportShrinkError,
    assert_safe_partial_write,
    atomic_write_json,
    backup_report,
    completed_plan_ids,
    load_existing_report,
    merge_partial_rerun,
    merge_session_results,
    plan_entry,
    report_plan_count,
)
from eval1.runtime_tuning import apply_fast_mode


def _attach_flow_miss_violation(dialogue: Dict[str, Any], path_id: str) -> None:
    """Record material path coverage gap before rule scoring."""
    flow = float(dialogue.get("flow_adherence_rate") or 0.0)
    if flow >= FLOW_COVERAGE_VIOLATION_THRESHOLD:
        return
    violations = list(dialogue.get("violations") or [])
    if any(
        str(v.get("violation_type") or "") == "flow_miss"
        and str(v.get("constraint_id") or "") == path_id
        for v in violations
    ):
        return
    violations.append(
        {
            "turn_index": max(1, len(dialogue.get("messages") or []) // 2),
            "violation_type": "flow_miss",
            "constraint_id": path_id,
            "constraint_text": f"测试路径 {path_id} 未按设计节点完整覆盖",
            "bot_utterance": "",
            "explanation": f"路径节点覆盖率 {flow:.0%}（低于 {FLOW_COVERAGE_VIOLATION_THRESHOLD:.0%} 阈值）",
            "deduction": round((1.0 - flow) * 20, 2),
        }
    )
    dialogue["violations"] = violations


class EvalRunner:
    """Phase 8+ end-to-end runner (layer1 -> layer2 -> layer3)."""

    async def run(
        self,
        dataset_id: str | None = None,
        max_plans: int | None = None,
        output_file: str | None = None,
        show_progress: bool = False,
        max_concurrent_dialogues: int | None = None,
        plan_timeout_sec: float | None = None,
        fast_mode: bool = False,
        skip_llm_judge: bool = False,
        include_control_group: bool = False,
        bot_provider: str = "qwen",
        plan_ids: List[str] | None = None,
        resume: bool = True,
    ) -> Dict[str, Any]:
        with bot_provider_scope(bot_provider) as active_bot:
            return await self._run_scoped(
                dataset_id=dataset_id,
                max_plans=max_plans,
                output_file=output_file,
                show_progress=show_progress,
                max_concurrent_dialogues=max_concurrent_dialogues,
                plan_timeout_sec=plan_timeout_sec,
                fast_mode=fast_mode,
                skip_llm_judge=skip_llm_judge,
                include_control_group=include_control_group,
                bot_provider=active_bot,
                plan_ids=plan_ids,
                resume=resume,
            )

    async def _run_scoped(
        self,
        *,
        dataset_id: str | None,
        max_plans: int | None,
        output_file: str | None,
        show_progress: bool,
        max_concurrent_dialogues: int | None,
        plan_timeout_sec: float | None,
        fast_mode: bool,
        skip_llm_judge: bool,
        include_control_group: bool,
        bot_provider: str,
        plan_ids: List[str] | None = None,
        resume: bool = True,
    ) -> Dict[str, Any]:
        bot_llm = get_bot_llm_profile(bot_provider)
        fast_meta = apply_fast_mode(enabled=fast_mode)
        if not fast_mode:
            from eval1.qwen_client import reset_llm_semaphore
            reset_llm_semaphore()
        scoring_cfg = ScoringConfig.from_settings()
        if not dataset_id:
            ds = list_eval1_datasets()
            if not ds:
                raise ValueError("No dataset found under eval1/data")
            dataset_id = ds[0]["dataset_id"]

        layer1 = await build_layer1_analysis(dataset_id)
        instruction = ParsedInstruction.model_validate(layer1.get("parsed") or {})
        paths = [
            EnumeratedPath.model_validate(p)
            for p in (layer1.get("paths") or [])
        ]

        dataset_variable_values = {
            str(k): str(v)
            for k, v in ((layer1.get("variable_values") or {}) if isinstance(layer1, dict) else {}).items()
        }
        # fallback to parsed variable values if dataset doesn't provide explicit values
        if not dataset_variable_values:
            parsed_vars = getattr(instruction, "variables", {}) or {}
            for k, vnode in parsed_vars.items():
                v = str(getattr(vnode, "value", "") or "").strip()
                if v:
                    dataset_variable_values[str(k)] = v
        all_plans, plan_build_meta = ExecutionPlanner().plan(
            paths,
            variable_values=dataset_variable_values,
            include_control_group=include_control_group,
        )
        plans, plan_select = select_execution_plans(all_plans, max_plans, plan_ids=plan_ids)
        plan_select = {**plan_select, **plan_build_meta}
        partial_rerun = bool(plan_ids)
        rerun_plan_ids = {p.plan_id for p in plans}
        plans_selected_total = len(plans)
        out = Path(output_file) if output_file else reports_output_path(str(dataset_id), bot_provider)
        existing_payload = load_existing_report(out)
        resume_enabled = bool(resume) and not partial_rerun
        completed_ids = completed_plan_ids(existing_payload) if resume_enabled and existing_payload else set()
        if partial_rerun:
            assert_safe_partial_write(
                partial_rerun=True,
                existing_payload=existing_payload,
                out_path=out,
                rerun_count=len(rerun_plan_ids),
                all_plans_total=len(all_plans),
            )
        elif not resume and existing_payload and report_plan_count(existing_payload) > 0:
            backup_path = backup_report(out, reason="no_resume")
            if show_progress and backup_path:
                print(f"[eval1] --no-resume：已备份 -> backups/{backup_path.name}", flush=True)
            existing_payload = None
            completed_ids = set()
        if resume_enabled and completed_ids:
            plans = [p for p in plans if p.plan_id not in completed_ids]
        checkpoint_base = existing_payload if (resume_enabled or partial_rerun) else None
        merge_meta: Dict[str, Any] = {
            "partial_rerun": partial_rerun,
            "resume_mode": resume_enabled,
            "plans_resumed": len(completed_ids),
            "plans_rerun": 0,
            "plans_reused": 0,
            "plans_missing": 0,
        }
        path_count = len(paths)
        persona_count = len(PersonaType)
        plans_expected = plan_select.get("plans_after_filter", plan_select["plans_total"])

        rule = RuleJudge()
        llm = LLMJudge(scoring=scoring_cfg)
        agg = Aggregator()
        use_judge = not skip_llm_judge
        concurrency = max(1, int(max_concurrent_dialogues or settings.max_concurrent_dialogues or 1))
        if plan_timeout_sec is not None and plan_timeout_sec > 0:
            timeout_sec = float(plan_timeout_sec)
        else:
            timeout_sec = float(settings.plan_timeout_sec) if settings.plan_timeout_sec > 0 else None

        total = len(plans)
        started_at = perf_counter()
        reports: List[EvalReport] = []
        dialogue_records: List[Dict[str, Any]] = []
        if show_progress and plans:
            mode = plan_select.get("coverage_mode", "full_cartesian")
            if partial_rerun:
                mode = f"partial_rerun({len(rerun_plan_ids)})"
            if plan_select["plans_truncated"] > 0:
                mode = f"truncated({plan_select['plans_selected']}/{plans_expected})"
            sem = int(plan_select.get("semantic_plan_total") or 0)
            contra = int(plan_select.get("potential_contradiction_total") or 0)
            hint = f" match={sem} annotated_contradiction={contra}" if contra else ""
            print(
                f"[eval1] dataset={dataset_id} paths={path_count} personas={persona_count} "
                f"plans={plan_select['plans_selected']}/{plans_expected} "
                f"(matrix={plan_select.get('plans_matrix_total', '?')}) "
                f"mode={mode}{hint}",
                flush=True,
            )
            if partial_rerun:
                if existing_payload:
                    cached_n = len(list((existing_payload.get("reports") or [])))
                    print(
                        f"[eval1] 部分重跑：执行 {len(rerun_plan_ids)} 条，"
                        f"其余 {max(0, cached_n - len(rerun_plan_ids))} 条复用缓存（{out.name}）",
                        flush=True,
                    )
                else:
                    print(
                        f"[eval1] 错误：{out.name} 无可用缓存，部分重跑已中止（避免覆盖全量数据）",
                        flush=True,
                    )
            elif resume_enabled and completed_ids:
                print(
                    f"[eval1] 断点续跑：已有 {len(completed_ids)}/{plans_selected_total} 条，"
                    f"本次执行 {len(plans)} 条（每条完成后自动保存到 {out.name}）",
                    flush=True,
                )
            if plan_select["plans_truncated"] == 0 and len(plans) >= 24:
                est_min = max(15, int(len(plans) / max(1, concurrency) * 2.5))
                fast_hint = " --fast" if fast_meta.get("fast_mode") else ""
                judge_hint = " --skip-judge" if skip_llm_judge else ""
                print(
                    f"[eval1] 全量评测预计约 {est_min}–{est_min * 2} 分钟（并发={concurrency}，"
                    f"每 plan 多轮 Bot+User+Judge LLM）。快速试跑可加："
                    f"--max-plans 12{fast_hint}{judge_hint}",
                    flush=True,
                )
        if not plans:
            if resume_enabled and existing_payload and report_plan_count(existing_payload) > 0:
                if show_progress:
                    print(
                        f"[eval1] 断点续跑：已完成 {report_plan_count(existing_payload)}/{plans_selected_total}，跳过执行",
                        flush=True,
                    )
                return dict(existing_payload)
            payload = {
                "dataset_id": dataset_id,
                "count": 0,
                "average_score": 0.0,
                "reports": [],
                "layer1_summary": layer1.get("summary", {}),
                "layer2": {"persona_registry": {}, "plans": [], "dialogues": []},
                "meta": {
                    "bot_provider": bot_provider,
                    "bot_model": bot_llm["model"],
                    "llm_model_main": bot_llm["model"],
                    "llm_model_fast": settings.llm_model_fast,
                    "judge_temperature": scoring_cfg.judge_temperature,
                    "num_judges_used": 1 if use_judge else 0,
                    "max_concurrent_dialogues": concurrency,
                    "llm_max_concurrent": int(settings.llm_max_concurrent),
                    "plan_timeout_sec": timeout_sec,
                    "fast_mode": bool(fast_meta.get("fast_mode")),
                    "path_count": path_count,
                    "persona_count": persona_count,
                    "plans_total": plans_expected,
                    "plans_selected": 0,
                    "plans_truncated": plans_expected,
                },
            }
            out = Path(output_file) if output_file else reports_output_path(str(dataset_id), bot_provider)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload

        semaphore = asyncio.Semaphore(concurrency)
        results: List[Tuple[EvalReport, Dict[str, Any]] | None] = [None] * total
        done_count = 0
        session_reports: Dict[str, EvalReport] = {}
        session_dialogues: Dict[str, Dict[str, Any]] = {}
        checkpoint_lock = asyncio.Lock()
        run_ctx = {
            "layer1": layer1,
            "paths": paths,
            "bot_llm": bot_llm,
            "scoring_cfg": scoring_cfg,
            "use_judge": use_judge,
            "concurrency": concurrency,
            "timeout_sec": timeout_sec,
            "fast_meta": fast_meta,
            "path_count": path_count,
            "persona_count": persona_count,
            "plan_select": plan_select,
            "include_control_group": include_control_group,
            "all_plans": all_plans,
        }

        async def _checkpoint_write() -> None:
            if not session_reports:
                return
            ck_reports, ck_dialogues, ck_meta = merge_session_results(
                all_plans=all_plans,
                new_reports=dict(session_reports),
                new_dialogues=dict(session_dialogues),
                existing_payload=checkpoint_base,
            )
            merged_ids = {r.plan_id for r in ck_reports}
            ck_plans = [plan_entry(p) for p in all_plans if p.plan_id in merged_ids]
            payload = self._build_run_payload(
                dataset_id=str(dataset_id),
                reports=ck_reports,
                dialogue_records=ck_dialogues,
                layer2_plans=ck_plans,
                merge_meta={**merge_meta, **ck_meta},
                bot_provider=bot_provider,
                run_ctx=run_ctx,
            )
            atomic_write_json(out, payload)

        async def _run_one(idx: int, plan) -> None:
            nonlocal done_count
            i = idx + 1
            plan_started = perf_counter()
            async with semaphore:
                if show_progress:
                    print(
                        f"[eval1] [{i}/{total}] start plan={plan.plan_id} path={plan.path.path_id} persona={plan.persona_type}",
                        flush=True,
                    )
                try:
                    coro = self._evaluate_one_plan(
                        dataset_id=str(dataset_id),
                        seq=i,
                        plan=plan,
                        instruction=instruction,
                        rule=rule,
                        llm=llm,
                        agg=agg,
                        scoring_cfg=scoring_cfg,
                        use_judge=use_judge,
                    )
                    report, dialogue_record = (
                        await asyncio.wait_for(coro, timeout=timeout_sec) if timeout_sec else await coro
                    )
                    status = "done"
                except asyncio.TimeoutError:
                    report, dialogue_record = self._make_timeout_result(
                        dataset_id=str(dataset_id),
                        seq=i,
                        plan=plan,
                        timeout_sec=float(timeout_sec or 0.0),
                    )
                    status = "timeout"
                except Exception as exc:
                    report, dialogue_record = self._make_error_result(
                        dataset_id=str(dataset_id),
                        seq=i,
                        plan=plan,
                        error=str(exc),
                    )
                    status = "error"

            results[idx] = (report, dialogue_record)
            async with checkpoint_lock:
                session_reports[report.plan_id] = report
                session_dialogues[str(dialogue_record.get("plan_id") or report.plan_id)] = dialogue_record
                await _checkpoint_write()
            done_count += 1
            if show_progress:
                elapsed = perf_counter() - started_at
                avg = elapsed / max(1, done_count)
                eta = max(0.0, avg * (total - done_count))
                llm_ok = int(bool(dialogue_record.get("user_llm_connected")) and bool(dialogue_record.get("bot_llm_connected")))
                bot_rounds = int(dialogue_record.get("trace_turn_count") or 0)
                print(
                    f"[eval1] [{i}/{total}] {status} score={report.total_score:.2f} "
                    f"msgs={report.total_turns} bot_rounds={bot_rounds} "
                    f"term={report.termination_reason} "
                    f"llm_ok={llm_ok}/1 plan_sec={perf_counter()-plan_started:.1f} eta_sec={eta:.1f}",
                    flush=True,
                )

        await asyncio.gather(*[_run_one(idx, p) for idx, p in enumerate(plans)])
        new_reports_map: Dict[str, EvalReport] = {}
        new_dialogues_map: Dict[str, Dict[str, Any]] = {}
        for item in results:
            if not item:
                continue
            report, dialogue_record = item
            new_reports_map[report.plan_id] = report
            new_dialogues_map[str(dialogue_record.get("plan_id") or report.plan_id)] = dialogue_record

        if partial_rerun and existing_payload:
            reports, dialogue_records, session_meta = merge_session_results(
                all_plans=all_plans,
                new_reports=new_reports_map,
                new_dialogues=new_dialogues_map,
                existing_payload=existing_payload,
            )
            merge_meta.update(session_meta)
            prev_n = report_plan_count(existing_payload)
            if len(reports) < prev_n:
                raise ReportShrinkError(
                    f"合并后仅 {len(reports)} 条，少于原报告 {prev_n} 条，已中止写入。"
                )
        elif partial_rerun:
            raise ReportShrinkError(
                f"部分重跑合并失败：{out.name} 缓存不可用。"
                f"请从 outputs/backups/ 或 Windows「以前的版本」恢复后重试。"
            )
        elif checkpoint_base is not None or new_reports_map:
            reports, dialogue_records, session_meta = merge_session_results(
                all_plans=all_plans,
                new_reports=new_reports_map,
                new_dialogues=new_dialogues_map,
                existing_payload=checkpoint_base,
            )
            merge_meta.update(session_meta)
        else:
            for item in results:
                if not item:
                    continue
                report, dialogue_record = item
                reports.append(report)
                dialogue_records.append(dialogue_record)
            merge_meta["plans_rerun"] = len(reports)

        merged_plan_ids = {r.plan_id for r in reports}
        layer2_plans = [plan_entry(p) for p in all_plans if p.plan_id in merged_plan_ids]
        payload = self._build_run_payload(
            dataset_id=str(dataset_id),
            reports=reports,
            dialogue_records=dialogue_records,
            layer2_plans=layer2_plans,
            merge_meta=merge_meta,
            bot_provider=bot_provider,
            run_ctx=run_ctx,
        )
        atomic_write_json(out, payload)
        if show_progress:
            reuse_hint = ""
            if merge_meta.get("plans_reused"):
                reuse_hint = f" reused={merge_meta['plans_reused']}"
            resumed_hint = ""
            if merge_meta.get("plans_resumed"):
                resumed_hint = f" resumed={merge_meta['plans_resumed']}"
            print(
                f"[eval1] complete dataset={dataset_id} plans={len(reports)} "
                f"avg_score={payload['average_score']}{reuse_hint}{resumed_hint} "
                f"total_sec={perf_counter()-started_at:.1f}",
                flush=True,
            )
        return payload

    def _build_run_payload(
        self,
        *,
        dataset_id: str,
        reports: List[EvalReport],
        dialogue_records: List[Dict[str, Any]],
        layer2_plans: List[Dict[str, Any]],
        merge_meta: Dict[str, Any],
        bot_provider: str,
        run_ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        layer1 = run_ctx["layer1"]
        paths = run_ctx["paths"]
        bot_llm = run_ctx["bot_llm"]
        scoring_cfg = run_ctx["scoring_cfg"]
        use_judge = run_ctx["use_judge"]
        concurrency = run_ctx["concurrency"]
        timeout_sec = run_ctx["timeout_sec"]
        fast_meta = run_ctx["fast_meta"]
        path_count = run_ctx["path_count"]
        persona_count = run_ctx["persona_count"]
        plan_select = run_ctx["plan_select"]
        include_control_group = run_ctx["include_control_group"]
        health = SystemHealthMetrics.from_dialogue_records(dialogue_records)
        dim_avg = self._dimension_averages(reports)
        grade_dist = self._grade_distribution(reports)
        return {
            "dataset_id": dataset_id,
            "count": len(reports),
            "average_score": round(sum(r.total_score for r in reports) / max(1, len(reports)), 2),
            "dimension_averages": dim_avg,
            "grade_distribution": grade_dist,
            "reports": [r.model_dump() for r in reports],
            "layer1_summary": layer1.get("summary", {}),
            "layer2": {
                "persona_registry": {
                    str(k.value): v.model_dump(mode="json")
                    for k, v in PERSONA_REGISTRY.items()
                },
                "plans": layer2_plans,
                "paths_by_id": {
                    p.path_id: {
                        "path_id": p.path_id,
                        "nodes": list(p.nodes or []),
                        "category_label": getattr(p, "category_label", "") or "",
                        "description": getattr(p, "description", "") or "",
                        "flow_description": getattr(p, "flow_description", "") or "",
                        "activated_rules": list(getattr(p, "activated_rules", None) or []),
                    }
                    for p in paths
                },
                "dialogues": dialogue_records,
            },
            "health": health.to_dict(),
            "meta": {
                "bot_provider": bot_provider,
                "bot_model": bot_llm["model"],
                "llm_model_main": bot_llm["model"],
                "llm_model_fast": settings.llm_model_fast,
                "judge_temperature": scoring_cfg.judge_temperature,
                "num_judges_used": 1 if use_judge else 0,
                "scoring": "single_judge_rubric_cot",
                "weight_rule": scoring_cfg.weight_rule,
                "weight_llm": scoring_cfg.weight_llm,
                "max_concurrent_dialogues": concurrency,
                "plan_timeout_sec": timeout_sec,
                "fast_mode": bool(fast_meta.get("fast_mode")),
                "path_count": path_count,
                "persona_count": persona_count,
                "plans_total": plan_select["plans_total"],
                "plans_selected": plan_select["plans_selected"],
                "plans_truncated": plan_select["plans_truncated"],
                "plans_skipped": plan_select.get("skipped_count", 0),
                "skipped_plans": plan_select.get("skipped_plans", []),
                "plans_matrix_total": plan_select.get("plans_matrix_total", plan_select["plans_total"]),
                "coverage_mode": plan_select.get("coverage_mode", "semantic_match"),
                "semantic_plan_total": plan_select.get("semantic_plan_total", 0),
                "control_plan_total": plan_select.get("control_plan_total", 0),
                "include_control_group": bool(include_control_group),
                "plans_rerun": int(merge_meta.get("plans_rerun") or 0),
                "plans_reused": int(merge_meta.get("plans_reused") or 0),
                "plans_missing": int(merge_meta.get("plans_missing") or 0),
                "plans_resumed": int(merge_meta.get("plans_resumed") or 0),
                "partial_rerun": bool(merge_meta.get("partial_rerun")),
                "resume_mode": bool(merge_meta.get("resume_mode")),
            },
        }

    async def _evaluate_one_plan(
        self,
        *,
        dataset_id: str,
        seq: int,
        plan,
        instruction,
        rule: RuleJudge,
        llm: LLMJudge,
        agg: Aggregator,
        scoring_cfg: ScoringConfig,
        use_judge: bool,
    ) -> Tuple[EvalReport, Dict[str, Any]]:
        sim = SimulationGraph()
        persona = PERSONA_REGISTRY[PersonaType(plan.persona_type)]
        dialogue = await sim.run_dialogue(plan, persona, instruction=instruction)
        _attach_flow_miss_violation(dialogue, plan.path.path_id)
        rule_ret = rule.score(plan, dialogue, instruction=instruction)
        rule_score = float(rule_ret["rule_score"])
        hard_fail = bool(rule_ret.get("hard_violation"))

        dim: Dict[str, float] = {}
        judge_degraded = False
        needs_human_review = bool(dialogue.get("pending_review"))
        judge_comment = ""
        top_improvement = ""
        dimension_evidence: List[Dict[str, Any]] = []
        if use_judge:
            jr = await llm.score(dialogue, instruction=instruction)
            llm_score = float(jr["llm_score"])
            dim = {k: float(v) for k, v in (jr.get("dimension_scores") or {}).items()}
            judge_degraded = bool(jr.get("degraded"))
            needs_human_review = needs_human_review or bool(jr.get("needs_human_review"))
            judge_comment = str(jr.get("judge_overall_comment") or jr.get("overall_comment") or "")
            top_improvement = str(jr.get("judge_top_improvement") or jr.get("top_improvement") or "")
            dimension_evidence = list(
                jr.get("judge_evidence_chain") or jr.get("evidence_chain") or []
            )
        else:
            llm_score = float(rule_score)
            dim = {k: float(rule_score) for k in DIMENSION_LABELS}

        aggregated = agg.aggregate(
            rule_score,
            llm_score,
            hard_fail=hard_fail,
            scoring=scoring_cfg,
        )
        score_breakdown = str(aggregated.get("score_breakdown") or "")
        termination = str(dialogue.get("termination_reason") or "unknown")
        flow_adherence = float(dialogue.get("flow_adherence_rate") or 0.0)

        violations: List[ViolationEvidence] = []
        for v in (dialogue.get("violations") or []):
            violations.append(
                ViolationEvidence(
                    turn_index=int(v.get("turn_index") or 1),
                    violation_type=str(v.get("violation_type") or "violation"),
                    constraint_id=str(v.get("constraint_id") or "unknown"),
                    constraint_text=str(v.get("constraint_text") or ""),
                    bot_utterance=str(v.get("bot_utterance") or ""),
                    explanation=str(v.get("explanation") or ""),
                    deduction=float(v.get("deduction") or 0.0),
                )
            )
        for v in (rule_ret.get("supplemental_violations") or []):
            if not isinstance(v, dict):
                continue
            violations.append(
                ViolationEvidence(
                    turn_index=int(v.get("turn_index") or 1),
                    violation_type=str(v.get("violation_type") or "flow_incomplete"),
                    constraint_id=str(v.get("constraint_id") or "F4"),
                    constraint_text=str(v.get("constraint_text") or ""),
                    bot_utterance=str(v.get("bot_utterance") or ""),
                    explanation=str(v.get("explanation") or ""),
                    deduction=float(v.get("deduction") or 10.0),
                )
            )

        report = EvalReport(
            report_id=f"{dataset_id}-r{seq}",
            plan_id=plan.plan_id,
            path_id=plan.path.path_id,
            persona_type=plan.persona_type,
            total_score=float(aggregated["total_score"]),
            grade=str(aggregated["grade"]),
            rule_score=float(rule_score),
            llm_score=float(llm_score),
            consistency_penalty=0.0,
            consistency_alert=False,
            consistency_kappa=1.0,
            consistency_note="",
            flow_adherence_rate=round(flow_adherence, 3),
            total_turns=len(dialogue.get("messages") or []),
            termination_reason=termination,
            violations=violations,
            dimension_scores={k: float(v) for k, v in dim.items()},
            score_breakdown=score_breakdown,
            judge_comment=judge_comment,
            top_improvement=top_improvement,
            dimension_evidence=dimension_evidence,
            summary=f"path={plan.path.path_id}, persona={plan.persona_type}, termination={termination}",
            improvement_suggestions=self._suggestions(
                flow_adherence, termination, hard_fail, int(dialogue.get("forced_action_retry_count") or 0)
            ),
            created_at=datetime.utcnow().isoformat(),
        )
        if top_improvement and top_improvement not in report.improvement_suggestions:
            report.improvement_suggestions.insert(0, top_improvement)
        if needs_human_review:
            report.improvement_suggestions.append("Action detection or judge scoring degraded; human review recommended.")
        trace = dict(dialogue.get("trace") or {})
        dialogue_record = {
            "report_id": report.report_id,
            "plan_id": plan.plan_id,
            "path_id": plan.path.path_id,
            "path_nodes": list(plan.path.nodes or []),
            "path_category_label": getattr(plan.path, "category_label", "") or "",
            "path_description": getattr(plan.path, "description", "") or "",
            "path_flow_description": getattr(plan.path, "flow_description", "") or "",
            "persona_type": plan.persona_type,
            "plan_group": getattr(plan, "plan_group", "semantic_match"),
            "plan_reason": plan.reason,
            "total_score": report.total_score,
            "grade": report.grade,
            "rule_score": report.rule_score,
            "llm_score": report.llm_score,
            "score_breakdown": report.score_breakdown,
            "dimension_scores": dict(report.dimension_scores or {}),
            "dimension_evidence": list(report.dimension_evidence or []),
            "judge_comment": report.judge_comment,
            "top_improvement": report.top_improvement,
            "termination_reason": termination,
            "path_covered": bool(dialogue.get("path_covered")),
            "flow_adherence_rate": round(flow_adherence, 3),
            "forced_action_retry_count": int(dialogue.get("forced_action_retry_count") or 0),
            "user_llm_connected": bool(dialogue.get("user_llm_connected")),
            "bot_llm_connected": bool(dialogue.get("bot_llm_connected")),
            "opening_line_match": bool(dialogue.get("opening_line_match")),
            "repetitive_bot_count": int(dialogue.get("repetitive_bot_count") or 0),
            "consistency_alert": False,
            "consistency_kappa": 1.0,
            "unknown_action_count": int(dialogue.get("unknown_action_count") or 0),
            "degraded_call_count": int(dialogue.get("degraded_call_count") or 0),
            "trace_turn_count": int(trace.get("turn_count") or len(trace.get("turns") or [])),
            "pending_review": bool(dialogue.get("pending_review")),
            "judge_degraded": judge_degraded,
            "bot_state": dict(dialogue.get("bot_state") or {}),
            "bot_state_log": list(dialogue.get("bot_state_log") or []),
            "messages": list(dialogue.get("messages") or []),
            "violations": [v.model_dump() for v in violations],
            "trace": trace,
        }
        return report, dialogue_record

    def _make_timeout_result(self, *, dataset_id: str, seq: int, plan, timeout_sec: float) -> Tuple[EvalReport, Dict[str, Any]]:
        violation = ViolationEvidence(
            turn_index=1,
            violation_type="plan_timeout",
            constraint_id="SYS_TIMEOUT",
            constraint_text=f"Per-plan timeout {timeout_sec:.0f}s",
            bot_utterance="",
            explanation="Plan execution exceeded timeout and was terminated.",
            deduction=100.0,
        )
        report = EvalReport(
            report_id=f"{dataset_id}-r{seq}",
            plan_id=plan.plan_id,
            path_id=plan.path.path_id,
            persona_type=plan.persona_type,
            total_score=0.0,
            grade="F",
            rule_score=0.0,
            llm_score=0.0,
            consistency_penalty=0.0,
            flow_adherence_rate=0.0,
            total_turns=0,
            termination_reason="plan_timeout",
            violations=[violation],
            dimension_scores={k: 0.0 for k in DIMENSION_WEIGHTS},
            summary=f"path={plan.path.path_id}, persona={plan.persona_type}, termination=plan_timeout",
            improvement_suggestions=["Increase --plan-timeout-sec or reduce --max-plans / turns / judges."],
            created_at=datetime.utcnow().isoformat(),
        )
        dialogue_record = {
            "report_id": report.report_id,
            "plan_id": plan.plan_id,
            "path_id": plan.path.path_id,
            "path_nodes": list(plan.path.nodes or []),
            "path_category_label": getattr(plan.path, "category_label", "") or "",
            "path_description": getattr(plan.path, "description", "") or "",
            "persona_type": plan.persona_type,
            "total_score": report.total_score,
            "grade": report.grade,
            "termination_reason": "plan_timeout",
            "path_covered": False,
            "flow_adherence_rate": 0.0,
            "forced_action_retry_count": 0,
            "user_llm_connected": False,
            "bot_llm_connected": False,
            "opening_line_match": False,
            "repetitive_bot_count": 0,
            "consistency_alert": False,
            "consistency_kappa": 0.0,
            "bot_state": {},
            "bot_state_log": [],
            "messages": [],
        }
        return report, dialogue_record

    def _make_error_result(self, *, dataset_id: str, seq: int, plan, error: str) -> Tuple[EvalReport, Dict[str, Any]]:
        violation = ViolationEvidence(
            turn_index=1,
            violation_type="runner_error",
            constraint_id="SYS_ERROR",
            constraint_text="Plan execution error",
            bot_utterance="",
            explanation=error[:500],
            deduction=100.0,
        )
        report = EvalReport(
            report_id=f"{dataset_id}-r{seq}",
            plan_id=plan.plan_id,
            path_id=plan.path.path_id,
            persona_type=plan.persona_type,
            total_score=0.0,
            grade="F",
            rule_score=0.0,
            llm_score=0.0,
            consistency_penalty=0.0,
            flow_adherence_rate=0.0,
            total_turns=0,
            termination_reason="runner_error",
            violations=[violation],
            dimension_scores={k: 0.0 for k in DIMENSION_WEIGHTS},
            summary=f"path={plan.path.path_id}, persona={plan.persona_type}, termination=runner_error",
            improvement_suggestions=["Inspect runner logs and retry this plan."],
            created_at=datetime.utcnow().isoformat(),
        )
        dialogue_record = {
            "report_id": report.report_id,
            "plan_id": plan.plan_id,
            "path_id": plan.path.path_id,
            "path_nodes": list(plan.path.nodes or []),
            "path_category_label": getattr(plan.path, "category_label", "") or "",
            "path_description": getattr(plan.path, "description", "") or "",
            "persona_type": plan.persona_type,
            "total_score": report.total_score,
            "grade": report.grade,
            "termination_reason": "runner_error",
            "path_covered": False,
            "flow_adherence_rate": 0.0,
            "forced_action_retry_count": 0,
            "user_llm_connected": False,
            "bot_llm_connected": False,
            "opening_line_match": False,
            "repetitive_bot_count": 0,
            "consistency_alert": False,
            "consistency_kappa": 0.0,
            "bot_state": {},
            "bot_state_log": [],
            "messages": [],
        }
        return report, dialogue_record

    @staticmethod
    def _dimension_averages(reports: List[EvalReport]) -> Dict[str, float]:
        if not reports:
            return {}
        sums = {d: 0.0 for d in DIMENSION_WEIGHTS}
        n = 0
        for r in reports:
            ds = r.dimension_scores or {}
            if not ds:
                continue
            n += 1
            for d in sums:
                sums[d] += float(ds.get(d, 0.0))
        if n == 0:
            return {}
        return {d: round(sums[d] / n, 2) for d in sums}

    @staticmethod
    def _grade_distribution(reports: List[EvalReport]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in reports:
            g = str(r.grade or "?")
            out[g] = out.get(g, 0) + 1
        return out

    def _suggestions(
        self,
        flow_adherence: float,
        termination: str,
        hard_fail: bool,
        forced_retries: int,
    ) -> List[str]:
        tips: List[str] = []
        if hard_fail:
            tips.append("Fix hard boundary constraints first; hard fail currently forces score to 0.")
        if flow_adherence < 0.85:
            tips.append("Improve transition prompts to keep dialogue on planned path.")
        if termination == "max_turns":
            tips.append("Add stronger closing trigger once path coverage is reached.")
        if forced_retries > 0:
            tips.append("Tighten action forcing prompts to reduce simulator retry count.")
        if not tips:
            tips.append("Current run is stable; keep monitoring consistency across personas.")
        return tips
