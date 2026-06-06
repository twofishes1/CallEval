from __future__ import annotations

from typing import Any, Dict, List, Set

_RETENTION_FSM_STATES = frozenset({"OBJECTION", "F3_RETAIN", "OBJ_FINAL"})
_REJECT_KEYWORDS = (
    "不想",
    "不太想",
    "拒绝",
    "不签",
    "不跑",
    "做不到",
    "太难",
    "不合理",
    "不接受",
    "算了",
    "不行",
    "不能",
    "放弃",
)
_RETENTION_INSTRUCTION_KEYWORDS = (
    "挽留",
    "不想配送",
    "鼓励能配送",
    "异议节点",
    "OBJECTION",
    "F3_RETAIN",
)


def instruction_supports_retention(instruction: Any | None) -> bool:
    """True only when Call Flow / task explicitly involves rider retention."""
    if not instruction:
        return True
    parts: List[str] = [
        str(getattr(instruction, "raw_text", "") or ""),
        str(getattr(instruction, "task_description", "") or getattr(instruction, "task", "") or ""),
    ]
    parts.extend(str(x) for x in (getattr(instruction, "flow_steps", []) or []))
    for c in getattr(instruction, "constraints", []) or []:
        parts.append(str(getattr(c, "text", c)))
    for kn in getattr(instruction, "knowledge_nodes", []) or []:
        parts.append(str(getattr(kn, "text", kn)))
    blob = "\n".join(parts)
    return any(k in blob for k in _RETENTION_INSTRUCTION_KEYWORDS)


def analyze_retention_context(
    dialogue: Dict[str, Any],
    instruction: Any | None = None,
) -> Dict[str, Any]:
    """
    Retention applies only when the instruction defines retention semantics AND
    the dialogue enters refusal / OBJECTION / F3_RETAIN / OBJ_FINAL.
    """
    retention_applicable = instruction_supports_retention(instruction)
    trace = dialogue.get("trace") or {}
    turns: List[Dict[str, Any]] = list(trace.get("turns") or [])
    covered: Set[str] = set(str(x) for x in (dialogue.get("covered_nodes") or []))
    visited: Set[str] = covered & set(_RETENTION_FSM_STATES)
    reject_turns: List[int] = []

    for t in turns:
        act = str(t.get("detected_action") or "")
        if act == "reject":
            reject_turns.append(int(t.get("turn_index") or 0))
        for key in ("fsm_state_before", "fsm_state_after"):
            st = str(t.get(key) or "")
            if st in _RETENTION_FSM_STATES:
                visited.add(st)

    for m in dialogue.get("messages") or []:
        if str(m.get("role", "")).lower() != "user":
            continue
        u = str(m.get("content") or "")
        if any(k in u for k in _REJECT_KEYWORDS):
            reject_turns.append(int(m.get("turn") or 0))

    retention_required = retention_applicable and (bool(visited) or bool(reject_turns))
    return {
        "retention_applicable": retention_applicable,
        "retention_required": retention_required,
        "retention_states_visited": sorted(visited),
        "user_reject_turns": sorted({t for t in reject_turns if t > 0}),
    }


def build_retention_judge_note(ctx: Dict[str, Any]) -> str:
    if not ctx.get("retention_applicable", True):
        return (
            "【挽留效果 — 本任务不适用】当前 Call Flow 不含「挽留/异议」节点（如直播升级通知类任务）。"
            "retention_effectiveness 维度不参与评分：reasoning 写「[任务不适用] 本任务无挽留场景」，"
            "score 可填 4，但勿引用轮次、勿列 key_issues。"
        )
    if ctx.get("retention_required"):
        states = ", ".join(ctx.get("retention_states_visited") or []) or "—"
        turns = ", ".join(str(t) for t in (ctx.get("user_reject_turns") or [])) or "—"
        return (
            "【挽留效果 — 本对话适用】用户曾拒绝/犹豫或路径经过异议·挽留节点"
            f"（{states}；用户拒绝相关轮次: T{turns}）。"
            "请按 Rubric 评估 Bot 的挽留策略是否有效。"
        )
    return (
        "【挽留效果 — 本对话不适用】全程用户配合、未进入 OBJECTION/F3_RETAIN/OBJ_FINAL，"
        "且无明确拒绝话术。顺流程下不要求主动挽留。"
        "retention_effectiveness 必须打 4 分，reasoning 注明「无拒绝场景，维度不适用」。"
        "禁止因未做挽留而扣 flow_adherence 或 retention 分。"
    )


def apply_retention_scoring_policy(result: Any, ctx: Dict[str, Any]) -> Any:
    """Override retention dimension when N/A; recompute weighted total."""
    from eval1.layer3.judge_types import DimensionJudgeScore, JudgeResult
    from eval1.layer3.rubrics import DIMENSION_WEIGHTS, compute_weighted_llm_score

    if ctx.get("retention_required"):
        return result

    skip_dims: Set[str] = set()
    new_dims: List[DimensionJudgeScore] = []
    for d in result.dimensions:
        if d.dimension != "retention_effectiveness":
            new_dims.append(d)
            continue

        if not ctx.get("retention_applicable", True):
            skip_dims.add("retention_effectiveness")
            new_dims.append(
                DimensionJudgeScore(
                    dimension=d.dimension,
                    score=4,
                    reasoning="[任务不适用] 本 Call Flow 不含挽留/异议节点，挽留效果维度不参与评分。",
                    evidence_turns=[],
                    key_issues=[],
                    weight=0.0,
                    applicable=False,
                )
            )
            continue

        issues = [
            x
            for x in (d.key_issues or [])
            if "挽留" not in str(x) and x != "missing_turn_evidence"
        ]
        new_dims.append(
            DimensionJudgeScore(
                dimension=d.dimension,
                score=4,
                reasoning=(
                    "[N/A] 用户全程未拒绝，未进入异议/挽留节点；挽留效果维度不适用，"
                    "按评测规则记 4 分（不因未主动挽留扣分）。"
                ),
                evidence_turns=d.evidence_turns or [1],
                key_issues=issues,
                weight=float(DIMENSION_WEIGHTS.get(d.dimension, d.weight)),
                applicable=True,
            )
        )

    scores = {d.dimension: d.score for d in new_dims}
    return JudgeResult(
        dimensions=new_dims,
        overall_comment=result.overall_comment,
        top_improvement=result.top_improvement,
        total_score=compute_weighted_llm_score(scores, skip_dims=skip_dims or None),
        raw_response=result.raw_response,
        is_fallback=result.is_fallback,
        degraded=result.degraded,
        needs_human_review=result.needs_human_review,
    )
