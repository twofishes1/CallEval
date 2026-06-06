from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool


class Eval1DatasetSummary(BaseModel):
    dataset_id: str
    name: str
    source_file: str
    instruction_preview: str


class Eval1AnalysisResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    parsed: Dict[str, Any]
    summary: Dict[str, Any]
    kg_viz: Dict[str, Any]
    conflicts: List[Dict[str, Any]]
    paths: List[Dict[str, Any]]
