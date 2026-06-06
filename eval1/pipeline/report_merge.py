from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from eval1.layer1.models import EvalReport, ExecutionPlan


class ReportShrinkError(ValueError):
    """Raised when a run would replace a larger report with fewer plans."""


def report_plan_count(payload: Dict[str, Any] | None) -> int:
    if not payload:
        return 0
    reports = payload.get("reports")
    if isinstance(reports, list) and reports:
        return len(reports)
    return int(payload.get("count") or 0)


def load_existing_report(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def backup_report(path: Path, *, reason: str = "pre_write") -> Path | None:
    """Copy current report to eval1/outputs/backups/ before overwrite."""
    if not path.exists():
        return None
    try:
        if path.stat().st_size <= 0:
            return None
    except OSError:
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"{path.stem}_{stamp}_{reason}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def list_report_backups(path: Path) -> List[Path]:
    backup_dir = path.parent / "backups"
    if not backup_dir.is_dir():
        return []
    return sorted(backup_dir.glob(f"{path.stem}_*{path.suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)


def restore_latest_backup(path: Path) -> Path:
    backups = list_report_backups(path)
    if not backups:
        raise FileNotFoundError(f"未找到 {path.name} 的备份文件（目录 outputs/backups/）")
    latest = backups[0]
    shutil.copy2(latest, path)
    return latest


def assert_safe_partial_write(
    *,
    partial_rerun: bool,
    existing_payload: Dict[str, Any] | None,
    out_path: Path,
    rerun_count: int,
    all_plans_total: int = 0,
) -> None:
    """Refuse partial runs that would wipe an existing multi-plan report."""
    if not partial_rerun:
        return
    existing_n = report_plan_count(existing_payload)
    if existing_payload is None or existing_n <= 0:
        raise ReportShrinkError(
            f"部分重跑已拒绝：{out_path.name} 不存在或为空。"
            f"若直接写入 {rerun_count} 条计划会覆盖全量数据。"
            f"请先完成全量评测，或从 Windows「以前的版本」/ outputs/backups/ 恢复后再试。"
        )
    expected = max(int(all_plans_total or 0), rerun_count + 1)
    min_ok = max(24, int(expected * 0.5))
    if existing_n < min_ok:
        raise ReportShrinkError(
            f"部分重跑已拒绝：{out_path.name} 当前仅 {existing_n} 条，"
            f"全量约 {all_plans_total} 条（至少需要 {min_ok} 条才允许部分重跑）。"
            f"请先恢复完整报告后再跑 D10/D9 等场景。"
        )


def _index_by_plan_id(items: List[Dict[str, Any]], key: str = "plan_id") -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        pid = str(item.get(key) or "").strip()
        if pid:
            out[pid] = item
    return out


def merge_partial_rerun(
    *,
    all_plans: List[ExecutionPlan],
    rerun_plan_ids: set[str],
    new_reports: Dict[str, EvalReport],
    new_dialogues: Dict[str, Dict[str, Any]],
    existing_payload: Dict[str, Any] | None,
) -> Tuple[List[EvalReport], List[Dict[str, Any]], Dict[str, int]]:
    """
    Merge freshly executed plan results with cached ones.

    Plans in ``rerun_plan_ids`` always prefer ``new_*``; all other plans reuse
    cached report/dialogue when present.
    """
    cached_reports = _index_by_plan_id(list((existing_payload or {}).get("reports") or []))
    cached_dialogues = _index_by_plan_id(
        list(((existing_payload or {}).get("layer2") or {}).get("dialogues") or [])
    )

    merged_reports: List[EvalReport] = []
    merged_dialogues: List[Dict[str, Any]] = []
    reused = 0
    rerun = 0
    missing = 0

    for plan in all_plans:
        pid = plan.plan_id
        if pid in rerun_plan_ids and pid in new_reports:
            merged_reports.append(new_reports[pid])
            if pid in new_dialogues:
                merged_dialogues.append(new_dialogues[pid])
            rerun += 1
            continue
        if pid in cached_reports:
            merged_reports.append(EvalReport.model_validate(cached_reports[pid]))
            if pid in cached_dialogues:
                merged_dialogues.append(dict(cached_dialogues[pid]))
            reused += 1
            continue
        missing += 1

    meta = {
        "plans_rerun": rerun,
        "plans_reused": reused,
        "plans_missing": missing,
        "partial_rerun": True,
    }
    return merged_reports, merged_dialogues, meta


def completed_plan_ids(payload: Dict[str, Any] | None) -> set[str]:
    if not payload:
        return set()
    ids: set[str] = set()
    for item in payload.get("reports") or []:
        if isinstance(item, dict):
            pid = str(item.get("plan_id") or "").strip()
            if pid:
                ids.add(pid)
    return ids


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def merge_session_results(
    *,
    all_plans: List[ExecutionPlan],
    new_reports: Dict[str, EvalReport],
    new_dialogues: Dict[str, Dict[str, Any]],
    existing_payload: Dict[str, Any] | None,
) -> Tuple[List[EvalReport], List[Dict[str, Any]], Dict[str, int]]:
    """Merge newly finished plans into an existing checkpoint (resume / partial rerun)."""
    return merge_partial_rerun(
        all_plans=all_plans,
        rerun_plan_ids=set(new_reports.keys()),
        new_reports=new_reports,
        new_dialogues=new_dialogues,
        existing_payload=existing_payload,
    )


def plan_entry(plan: ExecutionPlan) -> Dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "path_id": plan.path.path_id,
        "persona_type": plan.persona_type,
        "variable_values": dict(plan.variable_values or {}),
        "repeat_count": plan.repeat_count,
        "max_turns": plan.max_turns,
        "reason": plan.reason,
        "plan_group": getattr(plan, "plan_group", "semantic_match"),
    }
