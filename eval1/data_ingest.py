"""Parse uploaded eval data files into dataset records."""

from __future__ import annotations

import json
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

import openpyxl

DATA_DIR = Path(__file__).resolve().parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _guess_instruction_header(headers: List[str]) -> str:
    lowered = [h.lower() for h in headers]
    for cand in ("raw_instruction", "instruction", "content", "任务指令", "任务指令示例"):
        if cand.lower() in lowered:
            return headers[lowered.index(cand.lower())]
    for i, h in enumerate(headers):
        hl = h.lower()
        if "instruction" in hl or "指令" in h:
            return headers[i]
    skip = {"id", "dataset_id", "name", "variable_values", "variables"}
    candidates = [h for h in headers if h and h.lower() not in skip]
    return candidates[-1] if candidates else ""


def _normalize_dataset_id(raw: str) -> str:
    s = _as_str(raw)
    if s.isdigit():
        return f"instruction_{int(s)}"
    return s

_ALLOWED_SUFFIXES = {".xlsx", ".xlsm", ".json", ".txt", ".md"}


def _safe_filename(name: str) -> str:
    base = Path(name or "upload").name
    base = re.sub(r"[^\w.\-]+", "_", base).strip("._")
    return base or "upload.bin"


def parse_xlsx_bytes(content: bytes, source: str) -> List[Dict[str, Any]]:
    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return []

    headers = [_as_str(x) for x in rows[0]]
    col = {h.lower(): i for i, h in enumerate(headers)}
    inst_header = _guess_instruction_header(headers)
    inst_idx = headers.index(inst_header) if inst_header in headers else -1

    def cell(row: tuple[Any, ...], header: str) -> Any:
        idx = col.get(header.lower(), -1)
        if idx < 0 or idx >= len(row):
            return None
        return row[idx]

    out: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if not row or not any(row):
            continue
        did = _normalize_dataset_id(_as_str(cell(row, "dataset_id") or cell(row, "id")))
        name = _as_str(cell(row, "name")) or did
        variables_raw = cell(row, "variable_values") or cell(row, "variables")
        variables: Dict[str, str] = {}
        if isinstance(variables_raw, dict):
            variables = {str(k): _as_str(v) for k, v in variables_raw.items()}
        elif isinstance(variables_raw, str) and variables_raw.strip():
            try:
                parsed = json.loads(variables_raw)
                if isinstance(parsed, dict):
                    variables = {str(k): _as_str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                variables = {}

        instruction = ""
        if inst_idx >= 0 and inst_idx < len(row):
            instruction = _as_str(row[inst_idx])
        if not did or not instruction:
            continue
        out.append(
            {
                "dataset_id": did,
                "name": name or did,
                "raw_instruction": instruction,
                "variable_values": variables,
                "source_file": source,
            }
        )
    return out


def parse_json_bytes(content: bytes, source: str) -> List[Dict[str, Any]]:
    data = json.loads(content.decode("utf-8"))
    out: List[Dict[str, Any]] = []
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        did = _normalize_dataset_id(
            _as_str(item.get("dataset_id") or item.get("id") or item.get("instruction_id"))
        )
        instruction = _as_str(
            item.get("raw_instruction") or item.get("instruction") or item.get("content")
        )
        if not did or not instruction:
            continue
        variables = item.get("variable_values") or item.get("variables") or {}
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except json.JSONDecodeError:
                variables = {}
        if not isinstance(variables, dict):
            variables = {}
        out.append(
            {
                "dataset_id": did,
                "name": _as_str(item.get("name")) or did,
                "raw_instruction": instruction,
                "variable_values": {str(k): _as_str(v) for k, v in variables.items()},
                "source_file": source,
            }
        )
    return out


def parse_text_bytes(content: bytes, source: str, stem: str) -> List[Dict[str, Any]]:
    text = content.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    did = _normalize_dataset_id(stem) or f"upload_{int(time.time())}"
    return [
        {
            "dataset_id": did,
            "name": stem or did,
            "raw_instruction": text,
            "variable_values": {},
            "source_file": source,
        }
    ]


def parse_file_bytes(content: bytes, filename: str) -> List[Dict[str, Any]]:
    suffix = Path(filename or "").suffix.lower()
    source = f"upload:{filename}"
    if suffix in (".xlsx", ".xlsm"):
        return parse_xlsx_bytes(content, source)
    if suffix == ".json":
        return parse_json_bytes(content, source)
    if suffix in (".txt", ".md"):
        return parse_text_bytes(content, source, Path(filename).stem)
    raise ValueError(f"不支持的文件类型: {suffix or '(无扩展名)'}，请使用 .xlsx / .json / .txt")


def ingest_upload(content: bytes, filename: str) -> Dict[str, Any]:
    """Save upload under eval1/data/uploads and return parsed dataset summaries."""
    records = parse_file_bytes(content, filename)
    if not records:
        raise ValueError("文件中未解析到有效数据集（需包含 dataset_id 与指令正文）")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename)
    dest = UPLOAD_DIR / safe
    if dest.exists():
        dest = UPLOAD_DIR / f"{int(time.time())}_{safe}"
    dest.write_bytes(content)

    rel = dest.relative_to(DATA_DIR).as_posix()
    for r in records:
        r["source_file"] = f"eval1/data/{rel}"

    return {
        "stored_path": rel,
        "filename": dest.name,
        "count": len(records),
        "datasets": [
            {
                "dataset_id": r["dataset_id"],
                "name": r["name"],
                "source_file": r["source_file"],
                "instruction_preview": (
                    (r["raw_instruction"][:120] + "...")
                    if len(r["raw_instruction"]) > 120
                    else r["raw_instruction"]
                ),
            }
            for r in records
        ],
    }
