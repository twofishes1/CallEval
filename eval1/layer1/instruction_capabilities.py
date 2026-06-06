from __future__ import annotations

from eval1.layer3.retention_context import _RETENTION_INSTRUCTION_KEYWORDS


def instruction_has_retention_rails(instruction) -> bool:
    """True when Call Flow explicitly defines rider retention / F3_RETAIN semantics."""
    parts = [
        str(getattr(instruction, "raw_text", "") or ""),
        str(getattr(instruction, "task_description", "") or ""),
        str(getattr(instruction, "task", "") or ""),
    ]
    parts.extend(str(x) for x in (getattr(instruction, "flow_steps", []) or []))
    for c in getattr(instruction, "constraints", []) or []:
        parts.append(str(getattr(c, "text", c)))
    blob = "\n".join(parts)
    return any(k in blob for k in _RETENTION_INSTRUCTION_KEYWORDS)


def instruction_has_flow_branches(instruction) -> bool:
    """True when Call Flow uses conditional branches (instruction_2 style)."""
    from eval1.layer1.flow_branch_model import instruction_has_structured_branches

    return instruction_has_structured_branches(instruction)
