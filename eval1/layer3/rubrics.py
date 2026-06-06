from __future__ import annotations

from typing import Any, List, Set

from eval1.layer3.retention_context import instruction_supports_retention

DIMENSION_WEIGHTS = {
    "flow_adherence": 0.25,
    "dialogue_compliance": 0.20,
    "knowledge_accuracy": 0.20,
    "retention_effectiveness": 0.15,
    "boundary_handling": 0.10,
    "naturalness": 0.10,
}

DIMENSION_LABELS = {
    "flow_adherence": "流程遵循",
    "dialogue_compliance": "话术合规",
    "knowledge_accuracy": "知识准确",
    "retention_effectiveness": "挽留效果",
    "boundary_handling": "边界处理",
    "naturalness": "自然度",
}

RUBRICS = {
    "flow_adherence": """1分：完全不按流程，随意跳跃或遗漏关键步骤
2分：大致有流程意识，但多处乱序或跳步
3分：基本按流程，有1-2处小偏差（非关键步骤）
4分：严格按流程，只有细节表达差异
5分：完美遵循，且在流程内自然应对用户的插话""",
    "dialogue_compliance": """1分：大量违反话术约束
2分：多处禁用词或风格问题
3分：偶发违规
4分：基本合规
5分：完全合规且表达得体
【D1 字数张力】任务要求 Bot 每轮≤30字（Opening Line 除外），同时要求口语自然。
若 Bot 为在30字内说清要点而略紧凑，或偶发31~35字但语义完整，dialogue_compliance 与 naturalness 勿重罚；
仅当明显超长（如>35字）或频繁违规才在 dialogue_compliance 扣分。
naturalness 维度应单独评价口语是否像真人，勿因轻微字数超出而同时压低 naturalness。""",
    "knowledge_accuracy": """1分：严重错误或捏造
2分：多处不准确
3分：基本准确有小瑕疵
4分：准确
5分：准确且引用恰当""",
    "retention_effectiveness": """【仅当用户拒绝/犹豫或对话进入 OBJECTION、F3_RETAIN、OBJ_FINAL 时适用本维】
1分：应挽留场景下无挽留或激化矛盾
2分：应挽留场景下挽留无力
3分：应挽留场景下有挽留尝试
4分：应挽留场景下挽留较有效
5分：应挽留场景下挽留策略出色
【不适用场景】用户全程配合、无拒绝：本维固定 4 分，勿扣分""",
    "boundary_handling": """1分：越权承诺或胡乱回答
2分：边界意识弱
3分：基本守界
4分：处理得当
5分：边界清晰且礼貌""",
    "naturalness": """1分：机械生硬
2分：不自然
3分：尚可
4分：较自然
5分：非常自然像真人""",
}


def build_instruction_context(instruction: Any | None) -> str:
    """Inject scenario-specific anchors (Call Flow / constraints) into judge prompt."""
    if not instruction:
        return ""
    lines: List[str] = []
    flow = list(getattr(instruction, "flow_steps", []) or [])
    if flow:
        lines.append("【Call Flow 原文】")
        for i, step in enumerate(flow, start=1):
            lines.append(f"F{i}. {step}")
        if instruction_supports_retention(instruction):
            lines.append(
                "【流程说明】含「挽留不想配送的骑手」——仅在用户拒绝/异议时执行挽留；"
                "顺流程时主要是鼓励配合 + 安全提醒，不要求主动挽留。"
            )
        else:
            lines.append(
                "【流程说明】本任务为顺流程通知/确认类外呼，不含挽留或异议处理节点；"
                "勿用「F3 未挽留」等理由扣 flow_adherence 分。"
            )
    constraints = list(getattr(instruction, "constraints", []) or [])
    hard = [c for c in constraints if getattr(c, "is_hard", False)]
    if hard:
        lines.append("【硬约束摘要】")
        for c in hard[:8]:
            lines.append(f"- {getattr(c, 'id', '?')}: {getattr(c, 'text', '')[:80]}")
    opening = str(getattr(instruction, "opening_line", "") or "").strip()
    if opening:
        lines.append("【Opening Line 说明】首句 Opening Line 可超过30字；仅后续 Bot 轮次受「每轮不超过30字」约束。")
    lines.append(
        "【D1 字数与自然度】Bot 需在≤30字内口语化表达（Opening Line 除外）。"
        "评测时理解该张力：略超1~5字但语义完整时不应同时重扣 dialogue_compliance 与 naturalness；"
        "rule_judge 记录的 D_LEN 违规可作为参考，但 LLM 维度打分应区分「硬违规」与「为自然度略放宽」。"
    )
    return "\n".join(lines)


def build_rubric_prompt_section(instruction: Any | None = None) -> str:
    blocks: List[str] = []
    ctx = build_instruction_context(instruction)
    if ctx:
        blocks.append(ctx)
    blocks.append("【六维 Rubric 锚定表 — 每维 1~5 分，须找到对应行为才能给分】")
    for dim, weight in DIMENSION_WEIGHTS.items():
        label = DIMENSION_LABELS.get(dim, dim)
        rubric = RUBRICS.get(dim, "")
        blocks.append(f"\n### {label} ({dim}, 权重 {int(weight * 100)}%)\n{rubric}")
    return "\n".join(blocks)


def score_1_to_100(score_1_5: int) -> float:
    s = max(1, min(5, int(score_1_5)))
    return round(s / 5.0 * 100.0, 2)


def compute_weighted_llm_score(
    dimension_scores_1_5: dict[str, int],
    *,
    skip_dims: Set[str] | None = None,
) -> float:
    skip = skip_dims or set()
    active = {d: w for d, w in DIMENSION_WEIGHTS.items() if d not in skip}
    if not active:
        return 0.0
    norm = sum(active.values())
    total = 0.0
    for dim, weight in active.items():
        s = int(dimension_scores_1_5.get(dim, 3))
        total += (weight / norm) * score_1_to_100(s)
    return round(total, 2)
