# -*- coding: utf-8 -*-
"""Scan saved reports for dialogue coherence issues."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, List


def _find_message_lists(obj: Any, out: List[list]) -> None:
    if isinstance(obj, dict):
        msgs = obj.get("messages")
        if (
            isinstance(msgs, list)
            and msgs
            and isinstance(msgs[0], dict)
            and "role" in msgs[0]
            and "content" in msgs[0]
        ):
            out.append(msgs)
        for v in obj.values():
            _find_message_lists(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _find_message_lists(v, out)


def analyze_messages(msgs: Iterable[dict]) -> Counter:
    issues: Counter = Counter()
    messages = list(msgs)
    bots = [m["content"] for m in messages if m.get("role") == "bot"]
    users = [m["content"] for m in messages if m.get("role") == "user"]
    leak = re.compile(r"确认低延迟直播也已适用|进入第\d|参考话术|branch::")
    generic = re.compile(r"^(好的|可以|明白|嗯)[，,。.]?")

    for i in range(1, len(bots)):
        if bots[i].strip() and bots[i].strip() == bots[i - 1].strip():
            issues["bot_repeat"] += 1
    for b in bots:
        if leak.search(b):
            issues["bot_instruction_leak"] += 1
    for u in users:
        if len(u.strip()) <= 14 and generic.match(u.strip()):
            issues["user_generic"] += 1
    for i, u in enumerate(users):
        if i + 1 < len(bots) and bots[i + 1].strip() == bots[i].strip() if i < len(bots) else False:
            issues["user_talk_bot_repeat"] += 1
        if any(k in u for k in ("试用", "继续", "添加")) and i < len(bots) - 1:
            if bots[i + 1] == bots[i] if i < len(bots) else False:
                issues["user_progress_ignored"] += 1
    return issues


def scan_report(path: Path) -> Counter:
    data = json.loads(path.read_text(encoding="utf-8"))
    pools: List[list] = []
    _find_message_lists(data, pools)
    total: Counter = Counter()
    for msgs in pools:
        total.update(analyze_messages(msgs))
    total["dialogues"] = len(pools)
    return total


if __name__ == "__main__":
    root = Path("eval1/outputs")
    for p in sorted(root.glob("eval1_reports_instruction_*.json")):
        stats = scan_report(p)
        print(p.name, dict(stats))
