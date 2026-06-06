from __future__ import annotations

import re
from typing import Dict, List

from eval1.layer1.instruction_flow_normalizer import normalize_flow_and_knowledge
from eval1.layer1.models import Constraint, ConstraintType, KnowledgeNode, ParsedInstruction, VariableNode
from eval1.layer1.preprocessor import InstructionPreprocessor


class InstructionParserAgent:
    """Phase 3 parser with deterministic fallback rules."""

    async def parse(
        self,
        instruction_id: str,
        raw_text: str,
        variable_values: Dict[str, str] | None = None,
    ) -> ParsedInstruction:
        prep = InstructionPreprocessor().preprocess(raw_text)
        sections = prep.get("sections", {})
        resolved_values = self._resolve_variable_values(
            extracted=list((prep.get("variables") or {}).keys()),
            provided=variable_values or {},
        )
        sections = self._apply_variables_to_sections(sections, resolved_values)
        raw_flow = list(sections.get("call_flow") or [])
        raw_knowledge = list(sections.get("knowledge") or [])
        flow_steps, knowledge_items = normalize_flow_and_knowledge(raw_flow, raw_knowledge)
        constraint_lines = list(sections.get("constraints") or [])

        constraints: List[Constraint] = []
        constraints.extend(self._build_flow_constraints(flow_steps))
        constraints.extend(self._build_knowledge_constraints(knowledge_items))
        constraints.extend(self._build_text_constraints(constraint_lines))

        variables: Dict[str, VariableNode] = {}
        for name, meta in (prep.get("variables") or {}).items():
            variables[name] = VariableNode(
                name=name,
                value=str(resolved_values.get(name, "")),
                locations=list((prep.get("variable_locations") or {}).get(name, [])),
                semantic=str(meta.get("type") or ""),
            )
        # keep explicitly provided variables as well
        for name, val in resolved_values.items():
            if name in variables:
                continue
            variables[name] = VariableNode(
                name=name,
                value=str(val),
                locations=[],
                semantic="provided",
            )

        knowledge_nodes = self._build_knowledge_nodes(knowledge_items)
        has_conflicts = self._has_obvious_conflict(constraints)
        resolved_text = self._render_resolved_document(sections)

        return ParsedInstruction(
            instruction_id=instruction_id,
            raw_text=raw_text,
            resolved_text=resolved_text,
            role_description=str(sections.get("role") or "").strip(),
            task_description=str(sections.get("task") or "").strip(),
            opening_line=str(sections.get("opening_line") or "").strip(),
            flow_steps=flow_steps,
            constraints=constraints,
            knowledge_nodes=knowledge_nodes,
            variables=variables,
            has_conflicts=has_conflicts,
            resolved=False,
        )

    def _build_flow_constraints(self, flow_steps: List[str]) -> List[Constraint]:
        out: List[Constraint] = []
        for i, text in enumerate(flow_steps, start=1):
            out.append(
                Constraint(
                    id=f"F{i}",
                    type=ConstraintType.FLOW,
                    text=text,
                    priority=1,
                    is_hard=True,
                    measurable=True,
                    detection_rule=f"must_cover_flow_step:{i}",
                )
            )
        return out

    def _build_knowledge_constraints(self, knowledge_items: List[str]) -> List[Constraint]:
        out: List[Constraint] = []
        for i, text in enumerate(knowledge_items, start=1):
            out.append(
                Constraint(
                    id=f"K{i}",
                    type=ConstraintType.KNOWLEDGE,
                    text=text,
                    priority=2,
                    is_hard=False,
                    measurable=True,
                    detection_rule=f"faq_trigger:{i}",
                )
            )
        return out

    def _build_text_constraints(self, lines: List[str]) -> List[Constraint]:
        out: List[Constraint] = []
        d_idx = 1
        b_idx = 1
        for line in lines:
            txt = line.strip()
            if not txt:
                continue
            if re.search(r"(字数|字以内|不超过|≤|长度|30字)", txt):
                out.append(
                    Constraint(
                        id=f"D{d_idx}",
                        type=ConstraintType.DIALOGUE,
                        text=txt,
                        priority=2,
                        is_hard=True,
                        measurable=True,
                        detection_rule="utterance_length_check",
                    )
                )
                d_idx += 1
            elif re.search(r"(不能|禁止|边界|越权|无法|不支持|不属于)", txt):
                out.append(
                    Constraint(
                        id=f"B{b_idx}",
                        type=ConstraintType.BOUNDARY,
                        text=txt,
                        priority=1,
                        is_hard=True,
                        measurable=True,
                        detection_rule="boundary_violation_check",
                    )
                )
                b_idx += 1
            else:
                out.append(
                    Constraint(
                        id=f"D{d_idx}",
                        type=ConstraintType.DIALOGUE,
                        text=txt,
                        priority=3,
                        is_hard=False,
                        measurable=False,
                        detection_rule="llm_judge_only",
                    )
                )
                d_idx += 1
        return out

    def _build_knowledge_nodes(self, items: List[str]) -> List[KnowledgeNode]:
        out: List[KnowledgeNode] = []
        for i, text in enumerate(items, start=1):
            out.append(
                KnowledgeNode(
                    id=f"K{i}",
                    text=text,
                    trigger_type="on_user_ask",
                    trigger_keywords=self._extract_keywords(text),
                    variables=[],
                    precondition_nodes=[],
                    best_attach_state="FAQ_NORMAL",
                )
            )
        return out

    def _extract_keywords(self, text: str) -> List[str]:
        toks = re.split(r"[\s,，。；;:：/]+", text)
        toks = [t for t in toks if len(t) >= 2]
        return toks[:5]

    def _has_obvious_conflict(self, constraints: List[Constraint]) -> bool:
        lens = [c for c in constraints if c.type == ConstraintType.DIALOGUE]
        txts = [c.text for c in lens]
        return len(txts) != len(set(txts))

    def _render_resolved_document(self, sections: Dict[str, object]) -> str:
        parts: List[str] = []
        role = str(sections.get("role") or "").strip()
        task = str(sections.get("task") or "").strip()
        opening = str(sections.get("opening_line") or "").strip()
        if role:
            parts.append(f"## Role\n{role}")
        if task:
            parts.append(f"## Task\n{task}")
        if opening:
            parts.append(f"## Opening Line\n{opening}")
        flow = list(sections.get("call_flow") or [])
        if flow:
            parts.append("## Call Flow")
            parts.extend([f"{i}. {str(x).strip()}" for i, x in enumerate(flow, start=1)])
        knowledge = list(sections.get("knowledge") or [])
        if knowledge:
            parts.append("## FAQ / Knowledge")
            parts.extend([f"- {str(x).strip()}" for x in knowledge])
        constraints = list(sections.get("constraints") or [])
        if constraints:
            parts.append("## Constraints")
            parts.extend([f"- {str(x).strip()}" for x in constraints])
        return "\n\n".join(parts)

    def _resolve_variable_values(self, extracted: List[str], provided: Dict[str, str]) -> Dict[str, str]:
        resolved: Dict[str, str] = {}
        keys = set(extracted) | set(provided.keys())
        for k in keys:
            pv = str((provided or {}).get(k, "")).strip()
            if pv:
                resolved[k] = pv
            else:
                resolved[k] = self._default_for_var(k)
        return resolved

    def _default_for_var(self, name: str) -> str:
        n = str(name or "").strip()
        low = n.lower()
        if "rider" in low and "name" in low:
            return "张师傅"
        if "name" in low:
            return "客户"
        if n in {"X", "x"}:
            return "20"
        if n in {"Y", "y"}:
            return "30"
        if "phone" in low or "mobile" in low:
            return "13800000000"
        if "city" in low:
            return "上海"
        if "date" in low:
            return "今天"
        return "该项"

    def _apply_variables_to_sections(self, sections: Dict[str, object], values: Dict[str, str]) -> Dict[str, object]:
        def _render_text(txt: str) -> str:
            out = txt or ""
            # ${var}
            out = re.sub(
                r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}",
                lambda m: str(values.get(m.group(1), m.group(0))),
                out,
            )
            # **X ...** token
            out = re.sub(
                r"\*\*([A-Z])\s*([^*]*?)\*\*",
                lambda m: f"{values.get(m.group(1), m.group(1))}{m.group(2)}",
                out,
            )
            # bare single-letter variables like "Y天" / "X单"
            out = re.sub(
                r"(?<![A-Za-z0-9_])([A-Z])(?![A-Za-z0-9_])",
                lambda m: str(values.get(m.group(1), m.group(1))),
                out,
            )
            return out

        out: Dict[str, object] = dict(sections)
        for key in ("role", "task", "opening_line"):
            out[key] = _render_text(str(out.get(key) or ""))
        for key in ("call_flow", "knowledge", "constraints"):
            out[key] = [_render_text(str(x)) for x in list(out.get(key) or [])]
        return out
