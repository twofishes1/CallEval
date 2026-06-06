from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from eval1.config import settings
from eval1.layer2.robust_llm import RobustLLMCall
from eval1.layer3.judge_types import DimensionJudgeScore, JudgeResult
from eval1.layer3.rubrics import (
    DIMENSION_LABELS,
    DIMENSION_WEIGHTS,
    build_rubric_prompt_section,
    compute_weighted_llm_score,
    score_1_to_100,
)
from eval1.layer3.retention_context import (
    analyze_retention_context,
    apply_retention_scoring_policy,
    build_retention_judge_note,
)
from eval1.layer3.scoring_config import ScoringConfig

_TURN_CITE_RE = re.compile(r"\[T(\d+)\]")


class LLMJudge:
    def __init__(self, *, scoring: ScoringConfig | None = None) -> None:
        self.scoring = scoring or ScoringConfig.from_settings()
        self._llm = RobustLLMCall(component="judge")

    async def score(
        self,
        dialogue: Dict[str, Any],
        instruction: Any | None = None,
    ) -> Dict[str, Any]:
        msgs = dialogue.get("messages") or []
        transcript = "\n".join(
            [f"[T{m.get('turn', '?')}] {str(m.get('role', '')).upper()}: {m.get('content', '')}" for m in msgs]
        )
        rubric_block = build_rubric_prompt_section(instruction)
        retention_ctx = analyze_retention_context(dialogue, instruction)
        retention_note = build_retention_judge_note(retention_ctx)
        dim_keys = list(DIMENSION_WEIGHTS.keys())
        prompt = f"""
你是严格的多轮外呼 Bot 评测员。请按 Rubric 锚定为以下六个维度各打 1~5 分，并给出 CoT 推理。

{rubric_block}

{retention_note}

【CoT 强制规则】
- 每个维度的 reasoning 必须引用至少一个对话轮次，格式为 [T3] Bot说了…… 或 [T4] 用户……
- 若写不出 [Tn] 轮次证据，该维度最高只能给 2 分
- 禁止凭感觉打分，必须对照 Rubric 行为描述
- Opening Line（首句开场白）不受30字限制，勿因首句超长扣 dialogue_compliance 分
- D1≤30字与自然口语存在张力：Bot 后续轮次若31~35字但表达完整自然，dialogue_compliance 最高仍可给4分，勿与 naturalness 双重重罚；仅明显频繁超长才扣 dialogue_compliance
- 无用户拒绝时：勿在 flow_adherence 中因「F3 未挽留」扣分；挽留效果维度按上文「不适用」规则给 4 分

【输出 JSON 格式】
{{
  "dimensions": [
    {{
      "dimension": "flow_adherence",
      "score": 4,
      "reasoning": "[T2] Bot说明了合同生效…；[T5] 完成排名说明…",
      "evidence_turns": [2, 5],
      "key_issues": ["F4排名说明不完整"]
    }}
  ],
  "overall_comment": "一句话总评",
  "top_improvement": "最重要改进点"
}}

dimensions 必须包含且仅包含这六个 dimension 字段：
{", ".join(dim_keys)}

对话记录：
{transcript}
"""
        fallback_scores = {d: 3 for d in dim_keys}
        fallback = {
            "dimensions": [
                {
                    "dimension": d,
                    "score": 3,
                    "reasoning": f"[T1] 评测降级，使用默认分（{DIMENSION_LABELS.get(d, d)}）",
                    "evidence_turns": [1],
                    "key_issues": ["judge_degraded"],
                }
                for d in dim_keys
            ],
            "overall_comment": "Judge degraded; fallback scores applied.",
            "top_improvement": "",
        }

        async def _primary() -> str:
            return await self._llm.chat(
                system_prompt="你是严格的对话评测模型。只输出 JSON，每个维度必须有 [Tn] 轮次引用。",
                user_prompt=prompt,
                model=settings.llm_model_judge,
                temperature=float(self.scoring.judge_temperature),
                attempts=1,
            )

        text, status = await self._llm.call_with_fallback(
            primary_fn=_primary,
            fallback_value=json.dumps(fallback, ensure_ascii=False),
            validator=lambda s: "dimensions" in s,
            max_retry=2,
            timeout=30.0,
            tag="llm_judge",
        )
        degraded = status == "degraded"
        try:
            payload = self._extract_json_dict(text)
            result = self._parse_judge_payload(payload, degraded=degraded)
            result = apply_retention_scoring_policy(result, retention_ctx)
        except Exception:
            result = self._fallback_result(fallback_scores, degraded=True, reason="parse_error")
            result = apply_retention_scoring_policy(result, retention_ctx)

        dim_100 = {d.dimension: score_1_to_100(d.score) for d in result.dimensions}
        dim_1_5 = {d.dimension: d.score for d in result.dimensions}
        llm_score = float(result.total_score)
        return {
            "llm_score": round(llm_score, 2),
            "dimension_scores": dim_100,
            "dimension_scores_rubric": dim_1_5,
            "judge_evidence_chain": result.to_evidence_chain(),
            "judge_overall_comment": result.overall_comment,
            "judge_top_improvement": result.top_improvement,
            "retention_context": retention_ctx,
            "degraded": degraded or result.degraded,
            "needs_human_review": (degraded or result.degraded)
            and self.scoring.needs_human_review_on_degraded_judge,
        }

    def _parse_judge_json(self, raw: str) -> JudgeResult:
        payload = self._extract_json_dict(raw)
        return self._parse_judge_payload(payload, degraded=False)

    def _parse_judge_payload(self, payload: Dict[str, Any], *, degraded: bool) -> JudgeResult:
        raw_dims = payload.get("dimensions") or []
        by_name: Dict[str, Dict[str, Any]] = {}
        for item in raw_dims:
            if isinstance(item, dict):
                by_name[str(item.get("dimension", ""))] = item

        dimensions: List[DimensionJudgeScore] = []
        scores_1_5: Dict[str, int] = {}
        for dim, weight in DIMENSION_WEIGHTS.items():
            item = by_name.get(dim, {})
            score = max(1, min(5, int(item.get("score", 3))))
            reasoning = str(item.get("reasoning") or "").strip()
            evidence_turns = [int(x) for x in (item.get("evidence_turns") or []) if str(x).isdigit()]
            if not evidence_turns:
                evidence_turns = [int(m.group(1)) for m in _TURN_CITE_RE.finditer(reasoning)]
            key_issues = [str(x) for x in (item.get("key_issues") or []) if str(x).strip()]
            if not self._has_turn_evidence(reasoning, evidence_turns):
                score = min(score, 2)
                reasoning = (reasoning + " [证据不足，封顶2分]").strip()
                if "missing_turn_evidence" not in key_issues:
                    key_issues.append("missing_turn_evidence")
            scores_1_5[dim] = score
            dimensions.append(
                DimensionJudgeScore(
                    dimension=dim,
                    score=score,
                    reasoning=reasoning,
                    evidence_turns=evidence_turns,
                    key_issues=key_issues,
                    weight=float(weight),
                )
            )

        total = compute_weighted_llm_score(scores_1_5)
        return JudgeResult(
            dimensions=dimensions,
            overall_comment=str(payload.get("overall_comment") or ""),
            top_improvement=str(payload.get("top_improvement") or ""),
            total_score=total,
            raw_response=payload,
            is_fallback=degraded,
            degraded=degraded,
        )

    def _fallback_result(
        self,
        scores: Dict[str, int],
        *,
        degraded: bool,
        reason: str,
    ) -> JudgeResult:
        dimensions = [
            DimensionJudgeScore(
                dimension=d,
                score=int(scores.get(d, 3)),
                reasoning=f"[T1] fallback ({reason})",
                evidence_turns=[1],
                key_issues=[reason],
                weight=float(DIMENSION_WEIGHTS[d]),
            )
            for d in DIMENSION_WEIGHTS
        ]
        return JudgeResult(
            dimensions=dimensions,
            overall_comment="Judge fallback",
            top_improvement="",
            total_score=compute_weighted_llm_score(scores),
            is_fallback=True,
            degraded=degraded,
            needs_human_review=True,
        )

    @staticmethod
    def _has_turn_evidence(reasoning: str, evidence_turns: List[int]) -> bool:
        if evidence_turns:
            return True
        return bool(_TURN_CITE_RE.search(reasoning or ""))

    def _extract_json_dict(self, text: str) -> Dict[str, Any]:
        s = (text or "").strip()
        try:
            data = json.loads(s)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            raise ValueError("No JSON object found in judge output")
        data = json.loads(m.group(0))
        if not isinstance(data, dict):
            raise ValueError("Judge output JSON is not an object")
        return data
