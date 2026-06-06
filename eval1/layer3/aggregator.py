from __future__ import annotations

from typing import Dict

from eval1.layer3.scoring_config import ScoringConfig


class Aggregator:
    def aggregate(
        self,
        rule_score: float,
        llm_score: float,
        consistency_penalty: float = 0.0,
        hard_fail: bool = False,
        *,
        scoring: ScoringConfig | None = None,
    ) -> Dict[str, float | str | bool]:
        cfg = scoring or ScoringConfig.from_settings()
        if hard_fail:
            return {
                "total_score": 0.0,
                "grade": "F",
                "hard_fail": True,
                "score_breakdown": "hard_violation: 规则硬违规，总分置 0。",
            }
        total = max(
            0.0,
            min(
                100.0,
                rule_score * cfg.weight_rule + llm_score * cfg.weight_llm - consistency_penalty,
            ),
        )
        breakdown = (
            f"规则分={rule_score:.1f}×{cfg.weight_rule:.2f}+"
            f"LLM分={llm_score:.1f}×{cfg.weight_llm:.2f}"
        )
        if consistency_penalty > 0:
            breakdown += f"−一致性惩罚={consistency_penalty:.1f}"
        breakdown += f" => {round(total, 2)} ({cfg.grade_for_score(total)})"
        return {
            "total_score": round(total, 2),
            "grade": cfg.grade_for_score(total),
            "hard_fail": False,
            "score_breakdown": breakdown,
        }
