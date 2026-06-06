from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DimensionJudgeScore(BaseModel):
    dimension: str
    score: int = Field(ge=1, le=5)
    reasoning: str = ""
    evidence_turns: List[int] = Field(default_factory=list)
    key_issues: List[str] = Field(default_factory=list)
    weight: float = 0.0
    applicable: bool = True


class JudgeResult(BaseModel):
    dimensions: List[DimensionJudgeScore] = Field(default_factory=list)
    overall_comment: str = ""
    top_improvement: str = ""
    total_score: float = 0.0
    raw_response: Optional[Any] = None
    is_fallback: bool = False
    fallback_reason: str = ""
    degraded: bool = False
    needs_human_review: bool = False

    def to_evidence_chain(self) -> List[Dict[str, Any]]:
        return [d.model_dump() for d in self.dimensions]
