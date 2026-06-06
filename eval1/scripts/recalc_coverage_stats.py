#!/usr/bin/env python3
"""Recompute flow coverage / flow_miss from existing eval JSON (no Layer2 re-run)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval1.report.recalc_coverage import recalc_eval_payload  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline recalc path coverage stats from eval JSON")
    ap.add_argument(
        "--input",
        "-i",
        default="eval1/outputs/eval1_reports_instruction_1.json",
        help="Input eval report JSON (must include layer2.dialogues)",
    )
    ap.add_argument(
        "--output",
        "-o",
        default="",
        help="Optional output JSON path (default: print summary only)",
    )
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"File not found: {in_path}", file=sys.stderr)
        return 1

    payload = json.loads(in_path.read_text(encoding="utf-8"))
    dialogues = (payload.get("layer2") or {}).get("dialogues") or []
    if not dialogues:
        print("No layer2.dialogues in input — cannot recalc offline.", file=sys.stderr)
        return 1

    new_payload, delta = recalc_eval_payload(payload)

    print("=== 路径覆盖口径重算（未重跑 Layer2）===")
    print(f"用例数: {delta['cases']}")
    print(f"flow_miss 用例: {delta['flow_miss_old']} → {delta['flow_miss_new']}")
    print(f"综合均分: {delta['average_score_old']} → {delta['average_score_new']}")
    print(f"等级分布: {delta['grade_distribution_new']}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(new_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入: {out_path}")
    else:
        print("\n提示: 加 --output eval1/outputs/eval1_reports_recalc.json 可保存完整重算结果供 Layer3 加载")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
