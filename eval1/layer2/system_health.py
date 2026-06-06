from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SystemHealthMetrics:
    """Aggregate reliability metrics across a batch of dialogues."""

    total_dialogues: int = 0
    path_coverage_success_rate: float = 0.0
    action_detection_unknown_rate: float = 0.0
    llm_degraded_rate: float = 0.0
    avg_judge_kappa: float = 0.0
    timeout_rate: float = 0.0
    error_rate: float = 0.0

    @classmethod
    def from_dialogue_records(cls, records: List[Dict[str, Any]]) -> "SystemHealthMetrics":
        if not records:
            return cls()
        n = len(records)
        path_ok = sum(1 for r in records if bool(r.get("path_covered")))
        unknown_total = sum(int(r.get("unknown_action_count") or 0) for r in records)
        turn_total = sum(int(r.get("trace_turn_count") or len(r.get("trace", {}).get("turns") or [])) for r in records)
        degraded_total = sum(int(r.get("degraded_call_count") or 0) for r in records)
        kappas = [float(r.get("consistency_kappa") or 0.0) for r in records if r.get("consistency_kappa") is not None]
        timeouts = sum(1 for r in records if str(r.get("termination_reason") or "") == "plan_timeout")
        errors = sum(1 for r in records if str(r.get("termination_reason") or "") == "runner_error")

        return cls(
            total_dialogues=n,
            path_coverage_success_rate=round(path_ok / n, 3),
            action_detection_unknown_rate=round(unknown_total / max(1, turn_total), 3),
            llm_degraded_rate=round(degraded_total / max(1, n), 3),
            avg_judge_kappa=round(sum(kappas) / max(1, len(kappas)), 3) if kappas else 0.0,
            timeout_rate=round(timeouts / n, 3),
            error_rate=round(errors / n, 3),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_dialogues": self.total_dialogues,
            "path_coverage_success_rate": self.path_coverage_success_rate,
            "action_detection_unknown_rate": self.action_detection_unknown_rate,
            "llm_degraded_rate": self.llm_degraded_rate,
            "avg_judge_kappa": self.avg_judge_kappa,
            "timeout_rate": self.timeout_rate,
            "error_rate": self.error_rate,
            "alerts": self._alerts(),
        }

    def _alerts(self) -> List[str]:
        alerts: List[str] = []
        if self.path_coverage_success_rate < 0.90 and self.total_dialogues > 0:
            alerts.append("path_coverage_success_rate below 0.90")
        if self.action_detection_unknown_rate > 0.10:
            alerts.append("action_detection_unknown_rate above 0.10")
        if self.llm_degraded_rate > 0.05:
            alerts.append("llm_degraded_rate above 0.05")
        if self.timeout_rate > 0.05:
            alerts.append("timeout_rate above 0.05")
        if self.error_rate > 0.05:
            alerts.append("error_rate above 0.05")
        return alerts
