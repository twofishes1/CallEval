from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval1.bot_provider import reports_output_path
from eval1.pipeline.report_merge import list_report_backups, report_plan_count, restore_latest_backup


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List or restore eval1 report backups.")
    parser.add_argument("--dataset-id", type=str, default="instruction_2")
    parser.add_argument("--bot-provider", choices=["qwen", "deepseek"], default="qwen")
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore the newest backup over the live report file.",
    )
    parser.add_argument(
        "--restore-file",
        type=str,
        default=None,
        help="Restore a specific backup file path instead of the newest.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    target = reports_output_path(args.dataset_id, args.bot_provider)
    backups = list_report_backups(target)

    if args.restore_file:
        src = Path(args.restore_file)
        if not src.is_file():
            raise SystemExit(f"备份不存在: {src}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
        data = json.loads(target.read_text(encoding="utf-8"))
        print(f"已恢复 {target.name} <- {src.name} (count={report_plan_count(data)})")
        return

    if not backups:
        print(f"未找到 {target.name} 的自动备份（eval1/outputs/backups/）。")
        print("可尝试 Windows：右键该文件 → 属性 → 「以前的版本」")
        raise SystemExit(1)

    print(f"目标: {target}")
    for i, p in enumerate(backups[:10]):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            n = report_plan_count(data)
        except Exception:  # noqa: BLE001
            n = "?"
        print(f"  [{i + 1}] {p.name}  plans={n}  size={p.stat().st_size}")

    if args.restore:
        restored = restore_latest_backup(target)
        data = json.loads(target.read_text(encoding="utf-8"))
        print(f"已恢复最新备份 -> {target.name} (count={report_plan_count(data)}, from={restored.name})")


if __name__ == "__main__":
    main()
