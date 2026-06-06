from __future__ import annotations

from statistics import pstdev
from typing import Dict, List

from eval1.config import settings


class ConsistencyChecker:
    def check(self, judge_scores: List[float]) -> Dict[str, float]:
        if not judge_scores:
            return {
                "kappa": 0.0,
                "consistency_penalty": 0.0,
                "major_inconsistency": True,
                "std": 100.0,
            }
        if len(judge_scores) == 1:
            return {
                "kappa": 1.0,
                "consistency_penalty": 0.0,
                "major_inconsistency": False,
                "std": 0.0,
            }
        std = float(pstdev(judge_scores))
        # map std to pseudo kappa
        kappa = max(0.0, min(1.0, 1.0 - std / 40.0))
        penalty = 0.0
        major_inconsistency = bool(kappa < float(settings.kappa_threshold) and std >= 8.0)
        return {
            "kappa": round(kappa, 3),
            "consistency_penalty": round(penalty, 3),
            "major_inconsistency": major_inconsistency,
            "std": round(std, 3),
        }
