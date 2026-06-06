from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from eval1.config import settings


def normalize_weights(weight_rule: float, weight_llm: float) -> Tuple[float, float]:
    """Ensure rule + llm weights sum to 1.0."""
    wr = max(0.0, float(weight_rule))
    wl = max(0.0, float(weight_llm))
    total = wr + wl
    if total <= 0:
        return 0.5, 0.5
    if abs(total - 1.0) < 1e-6:
        return wr, wl
    return wr / total, wl / total


@dataclass
class ScoringConfig:
    """Single LLM judge + rule score. Weights always sum to 1.0."""

    weight_rule: float = 0.40
    weight_llm: float = 0.60
    grade_thresholds: List[float] = field(default_factory=lambda: [90.0, 80.0, 70.0, 60.0])
    judge_temperature: float = 0.10
    llm_fallback_score: float = 65.0
    needs_human_review_on_degraded_judge: bool = True

    def __post_init__(self) -> None:
        wr, wl = normalize_weights(self.weight_rule, self.weight_llm)
        self.weight_rule = wr
        self.weight_llm = wl

    @classmethod
    def from_settings(cls) -> "ScoringConfig":
        wr, wl = normalize_weights(
            float(settings.weight_rule),
            float(settings.weight_llm),
        )
        return cls(
            weight_rule=wr,
            weight_llm=wl,
            judge_temperature=float(getattr(settings, "judge_temperature", 0.10)),
            llm_fallback_score=65.0,
        )

    @property
    def weight_sum(self) -> float:
        return self.weight_rule + self.weight_llm

    def get_judge_count(self, *, skip: bool = False) -> int:
        return 0 if skip else 1

    def grade_for_score(self, total: float) -> str:
        t = self.grade_thresholds
        if total >= t[0]:
            return "A"
        if total >= t[1]:
            return "B"
        if total >= t[2]:
            return "C"
        if total >= t[3]:
            return "D"
        return "F"
