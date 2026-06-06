from __future__ import annotations

import re
from typing import List, Tuple

from eval1.layer1.flow_branch_extract import is_flow_branch_line

# Top-level Call Flow node (becomes F1..FN — path enumeration stays on these)
_MAIN_STEP_RE = re.compile(
    r"^(?:#{1,3}\s*)?(?:step\s*)?(\d+)[:：\.]\s*(.+)$",
    re.IGNORECASE,
)
_NUM_STEP_RE = re.compile(r"^(\d+)\.\s+(.+)$")

# Lines that are NOT standalone FSM nodes — go to knowledge / annex (not branch lines)
_META_NAV_RE = re.compile(
    r"(请其转达|然后进入|每步暂停)",
    re.IGNORECASE,
)
_FAQ_HINT_RE = re.compile(
    r"(区别|价格|知识库|参考话术|标准直播|低延迟|询问|Web控制台|校务系统|SaaS|企业微信|收费规则|线路)",
    re.IGNORECASE,
)
_SKIP_AS_STEP_RE = re.compile(
    r"^(?:[-*•]\s*)?(?:\*\*)?(?:参考话术|询问|若|如果|when|Web控制台|第三方系统)",
    re.IGNORECASE,
)


def _clean_step_title(num: str, title: str) -> str:
    t = re.sub(r"\*+", "", title).strip()
    t = re.sub(r"^[-•]\s*", "", t).strip()
    # FSM 内部用纯业务描述，不带 Step N: 标签（避免 Bot 照读）
    return t if t else f"步骤{num}"


def normalize_flow_and_knowledge(
    call_flow: List[str],
    existing_knowledge: List[str] | None = None,
) -> Tuple[List[str], List[str]]:
    """
    Split raw call_flow lines into:
    - main_flow_steps: logical steps for FSM F1..FN (path coverage)
    - knowledge_items: FAQ / scripts (branch lines excluded — they become BR nodes in RuleGraph)
    """
    knowledge: List[str] = [
        str(x).strip()
        for x in (existing_knowledge or [])
        if str(x).strip() and not is_flow_branch_line(str(x).strip())
    ]
    main_steps: List[str] = []
    seen_main: set[str] = set()

    stripped_flow = [str(x).strip() for x in (call_flow or []) if str(x).strip()]
    # Instruction-1 style: 4 plain numbered-step sentences (number stripped by preprocessor)
    if stripped_flow and len(stripped_flow) <= 12:
        if all(
            not _MAIN_STEP_RE.match(line) and not _NUM_STEP_RE.match(line)
            for line in stripped_flow
        ):
            return stripped_flow, knowledge

    for raw in call_flow or []:
        line = str(raw).strip()
        if not line:
            continue

        m_main = _MAIN_STEP_RE.match(line)
        if not m_main:
            m_num = _NUM_STEP_RE.match(line)
            if m_num and not line.lstrip().startswith("-"):
                m_main = m_num

        if m_main:
            step_line = _clean_step_title(m_main.group(1), m_main.group(2))
            if step_line not in seen_main:
                seen_main.add(step_line)
                main_steps.append(step_line)
            continue

        if is_flow_branch_line(line):
            continue

        if _SKIP_AS_STEP_RE.match(line) or _META_NAV_RE.search(line):
            if line not in knowledge:
                knowledge.append(line)
            continue

        if _FAQ_HINT_RE.search(line) or line.startswith(("-", "*", "•")) or "**" in line:
            cleaned = re.sub(r"^[-*•]\s*", "", line).strip()
            if cleaned and cleaned not in knowledge:
                knowledge.append(cleaned)
            continue

        if len(line) >= 12:
            if line not in knowledge:
                knowledge.append(line)
        elif _META_NAV_RE.search(line):
            if line not in knowledge:
                knowledge.append(line)

    # Fallback: keep numbered lines only (instruction 1 style)
    if not main_steps:
        for raw in call_flow or []:
            line = str(raw).strip()
            m = _NUM_STEP_RE.match(line)
            if m and not line.startswith("-"):
                step_line = f"{m.group(1)}. {m.group(2).strip()}"
                if step_line not in seen_main:
                    seen_main.add(step_line)
                    main_steps.append(step_line)

    # Last resort: don't lose data — treat original as main if small enough
    if not main_steps and call_flow:
        compact = [str(x).strip() for x in call_flow if str(x).strip()]
        if len(compact) <= 12:
            main_steps = compact
        else:
            # too many lines: take Step headers only
            for line in compact:
                m = re.search(r"step\s*(\d+)[:：]\s*(.+)", line, re.I)
                if m:
                    step_line = _clean_step_title(m.group(1), m.group(2))
                    if step_line not in seen_main:
                        seen_main.add(step_line)
                        main_steps.append(step_line)

    return main_steps, knowledge
