"""Load datasets from eval1/data (builtin xlsx + uploads/)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from eval1.data_ingest import UPLOAD_DIR, parse_file_bytes, parse_xlsx_bytes

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_all_datasets() -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    xlsx = DATA_DIR / "data.xlsx"
    if xlsx.exists():
        for rec in parse_xlsx_bytes(xlsx.read_bytes(), "eval1/data/data.xlsx"):
            merged[rec["dataset_id"]] = rec

    if UPLOAD_DIR.is_dir():
        for path in sorted(UPLOAD_DIR.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                records = parse_file_bytes(path.read_bytes(), path.name)
            except Exception:
                continue
            rel = path.relative_to(DATA_DIR).as_posix()
            for rec in records:
                merged[rec["dataset_id"]] = {
                    **rec,
                    "source_file": f"eval1/data/{rel}",
                }

    return list(merged.values())


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    for item in load_all_datasets():
        if item["dataset_id"] == dataset_id:
            return item
    return None


def list_dataset_summaries() -> List[Dict[str, Any]]:
    out = []
    for d in load_all_datasets():
        text = d["raw_instruction"]
        out.append(
            {
                "dataset_id": d["dataset_id"],
                "name": d["name"],
                "source_file": d["source_file"],
                "instruction_preview": (text[:120] + "...") if len(text) > 120 else text,
            }
        )
    return out
