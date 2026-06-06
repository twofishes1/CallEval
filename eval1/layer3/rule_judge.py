from __future__ import annotations

from typing import Any, Dict, List

from eval1.layer1.models import ExecutionPlan
from eval1.layer2.instruction_injection import f4_coverage_summary, instruction_f4_is_delivery_split


def _deduction_by_priority(*, is_hard: bool, priority: int) -> float:
    if is_hard:
        return 20.0
    if priority == 1:
        return 10.0
    if priority in (2, 3):
        return 7.0
    return 5.0


def _f4_delivery_coverage_applies(instruction: Any | None, path_nodes: List[str]) -> bool:
    """F4 三要点覆盖率仅适用于配送任务的 F4 拆分步骤。"""
    if "F4" not in path_nodes:
        return False
    if instruction is None:
        return False
    steps = list(getattr(instruction, "flow_steps", []) or [])
    step4 = str(steps[3]) if len(steps) >= 4 else ""
    return instruction_f4_is_delivery_split(instruction, step4)


class RuleJudge:
    def score(
        self,
        plan: ExecutionPlan,
        dialogue: Dict[str, Any],
        instruction: Any | None = None,
    ) -> Dict[str, float | bool]:
        violations: List[Dict[str, Any]] = list(dialogue.get("violations") or [])
        flow_rate = float(dialogue.get("flow_adherence_rate") or 0.0)
        hard_violation = bool(dialogue.get("hard_violation"))

        total_deduction = 0.0
        hard_count = 0
        seen: set[str] = set()

        for v in violations:
            cid = str(v.get("constraint_id") or "")
            key = f"{cid}:{v.get('turn_index')}"
            if key in seen:
                continue
            seen.add(key)
            vtype = str(v.get("violation_type") or "")
            ded = float(v.get("deduction") or 0.0)
            if ded <= 0:
                if vtype == "hard_boundary":
                    ded = 20.0
                elif vtype == "dialogue_length":
                    ded = 7.0
                elif vtype == "flow_miss":
                    ded = max(5.0, (1.0 - flow_rate) * 20.0)
                elif vtype == "flow_incomplete":
                    ded = 10.0
                else:
                    ded = 5.0
            if vtype == "hard_boundary" or ded >= 20.0:
                hard_count += 1
            total_deduction += ded

        bot_state = dict(dialogue.get("bot_state") or {})
        path_nodes = list(getattr(getattr(plan, "path", None), "nodes", None) or [])
        if _f4_delivery_coverage_applies(instruction, path_nodes):
            f4_cov = f4_coverage_summary(bot_state)
            if f4_cov.get("entered") and not f4_cov.get("complete"):
                missing = list(f4_cov.get("missing") or [])
                violations.append(
                    {
                        "turn_index": max(1, len(dialogue.get("messages") or []) // 2),
                        "violation_type": "flow_incomplete",
                        "constraint_id": "F4",
                        "constraint_text": "第4步排名/拒单/天气要点未说全",
                        "bot_utterance": "",
                        "explanation": f"F4 missing: {', '.join(missing)}",
                        "deduction": 10.0,
                    }
                )
                total_deduction += 10.0

        if flow_rate < 0.6:
            total_deduction += 10.0
        elif flow_rate < 0.85:
            total_deduction += 5.0

        repetitive_bot_count = int(dialogue.get("repetitive_bot_count") or 0)
        if repetitive_bot_count > 0:
            total_deduction += min(15.0, repetitive_bot_count * 4.0)

        if not bool(dialogue.get("opening_line_match", False)):
            total_deduction += 8.0

        if hard_count > 2:
            hard_violation = True

        score = max(0.0, 100.0 - total_deduction)
        extra: List[Dict[str, Any]] = []
        if _f4_delivery_coverage_applies(instruction, path_nodes):
            f4_cov = f4_coverage_summary(bot_state)
            if f4_cov.get("entered") and not f4_cov.get("complete"):
                extra.append(violations[-1] if violations and violations[-1].get("constraint_id") == "F4" else {})
        extra = [v for v in extra if v]
        return {
            "rule_score": round(score, 2),
            "hard_violation": hard_violation,
            "rule_deduction_total": round(total_deduction, 2),
            "hard_violation_count": hard_count,
            "supplemental_violations": [
                v for v in violations if v.get("constraint_id") == "F4" and v.get("violation_type") == "flow_incomplete"
            ],
        }
