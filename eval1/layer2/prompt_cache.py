from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Tuple


def _slots_key(slots: Dict[str, str] | None) -> str:
    items = sorted((str(k), str(v)) for k, v in (slots or {}).items())
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


class BotPromptCache:
    """Cache heavy bot system prompts per instruction + slot values."""

    def __init__(self) -> None:
        self._sys: Dict[str, str] = {}
        self._warnings: Dict[str, list[str]] = {}

    def get_system_prompt(
        self,
        *,
        instruction_id: str,
        slots: Dict[str, str] | None,
        builder,
    ) -> Tuple[str, list[str]]:
        key = f"{instruction_id}:{_slots_key(slots)}"
        if key not in self._sys:
            body, warnings = builder()
            prefix = (
                "你是被测Bot，必须100%按下方任务指令原文执行，扮演指令中的角色对外呼骑手。\n"
                "你不是通用客服，不要输出与当前步骤无关的话。\n"
                "严格遵循下方 Constraints：避免重复回复；如需重申须换种方式表达；"
                "遵循 Call Flow 与 Knowledge/FAQ；骑手坚持无法配送则安慰后挂断。\n"
                "每次回复不超过30字，中文口语自然，像站长打电话。"
                "在30字内尽量用完整短句，不要为省字而拆成电报体；"
                "Opening Line 除外，其余轮次遵守 D1 字数约束。\n"
                "禁止泛回复：如「收到，我们继续下一步」。\n"
                "禁止读出流程步骤原文或元指令（如「说明…」「确认…」「Step1/Step5」）。\n"
                "禁止询问指令未写明的细节（如具体校区名、具体人数）；身份确认按 Opening Line 一次即可。\n"
                "用户姓名仅在开场白用一次，后续不要每句都叫名字。\n"
                "【硬性约束】只能引用任务指令、Opening Line、Call Flow、FAQ、Constraints 中已有表述。\n"
                "用户质疑时优先用 FAQ 换种说法，禁止逐字复读 Call Flow 或上一轮 Bot 话。\n"
                "禁止编造具体时间点（如11点、13点）、单量、天数、规则；FAQ/原文没有的内容用边界话术回应。\n\n"
            )
            self._sys[key] = prefix + body
            self._warnings[key] = list(warnings or [])
        return self._sys[key], list(self._warnings.get(key) or [])


# Shared per-process cache (BotWrapper instances also hold one)
GLOBAL_BOT_PROMPT_CACHE = BotPromptCache()
