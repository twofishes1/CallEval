from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

import networkx as nx

from eval1.layer1.flow_branch_extract import extract_branches_from_block, iter_step_blocks
from eval1.layer1.flow_branch_model import StructuredBranch, parse_instruction_branches
from eval1.layer1.instruction_capabilities import instruction_has_flow_branches, instruction_has_retention_rails
from eval1.layer1.models import ConstraintType, ParsedInstruction


@dataclass
class ConflictItem:
    conflict_id: str
    conflict_type: str
    description: str
    node_ids: List[str]
    severity: str = "warning"


class RuleGraphBuilder:
    """Phase 4 Rule KG (flow graph + rule attachments)."""

    def __init__(self, instruction: ParsedInstruction) -> None:
        self.instruction = instruction
        self.g = nx.DiGraph()
        self.flow_nodes: List[str] = []
        self.attachment: Dict[str, List[str]] = {}

    @classmethod
    def build_from_instruction(cls, instruction: ParsedInstruction) -> "RuleGraphBuilder":
        inst = cls(instruction)
        inst.build()
        return inst

    def build(self):
        self.g.clear()
        self._build_flow_layer()
        _attach_flow_branches_and_ops(self.g, self.instruction.raw_text, self.flow_nodes)
        self._attach_constraints()
        self._attach_knowledge()
        self._attach_globals()
        return self

    def _add_node(self, node_id: str, node_type: str, label: str, **attrs) -> None:
        self.g.add_node(node_id, node_type=node_type, label=label, **attrs)

    def _build_flow_layer(self) -> None:
        self._add_node("START", "meta", "START")
        self._add_node("END", "meta", "END")
        self._add_node("FAQ_NORMAL", "transition", "FAQ_NORMAL")
        self._add_node("FAQ_OOB", "transition", "FAQ_OOB")
        self._add_node("OBJECTION", "transition", "OBJECTION")
        self._retention_rails = instruction_has_retention_rails(self.instruction)
        if self._retention_rails:
            self._add_node("F3_RETAIN", "transition", "F3_RETAIN")
            self._add_node("OBJ_FINAL", "transition", "OBJ_FINAL")
        self._add_node("CLOSING", "transition", "CLOSING")

        flow_count = len(self.instruction.flow_steps or [])
        self.flow_nodes = []
        for i, step in enumerate(self.instruction.flow_steps or [], start=1):
            nid = f"F{i}"
            self.flow_nodes.append(nid)
            self._add_node(nid, "flow_step", step, step_index=i)

        if not self.flow_nodes:
            self.g.add_edge("START", "CLOSING", edge_type="sequence", guard_expr="true", edge_confidence=1.0)
            self.g.add_edge("CLOSING", "END", edge_type="sequence", guard_expr="true", edge_confidence=1.0)
            return

        self.g.add_edge("START", self.flow_nodes[0], edge_type="sequence", guard_expr="true", edge_confidence=1.0)
        for a, b in zip(self.flow_nodes[:-1], self.flow_nodes[1:]):
            self.g.add_edge(a, b, edge_type="sequence", guard_expr="flow_progress", edge_confidence=1.0)
        self.g.add_edge(self.flow_nodes[-1], "CLOSING", edge_type="sequence", guard_expr="all_steps_done", edge_confidence=0.95)
        self.g.add_edge("CLOSING", "END", edge_type="sequence", guard_expr="closing_done", edge_confidence=1.0)

        # interruption rails
        self.g.add_edge("START", "OBJECTION", edge_type="branch", guard_expr="user_refusal", edge_confidence=0.6)
        for f in self.flow_nodes:
            self.g.add_edge(f, "OBJECTION", edge_type="branch", guard_expr="user_refusal", edge_confidence=0.75)
            self.g.add_edge(f, "FAQ_NORMAL", edge_type="branch", guard_expr="user_asks_faq", edge_confidence=0.8)
            self.g.add_edge(f, "FAQ_OOB", edge_type="branch", guard_expr="user_oob_question", edge_confidence=0.55)

        # retention jump (instruction_1 style only)
        if self._retention_rails:
            self.g.add_edge("START", "F3_RETAIN", edge_type="retention_jump", guard_expr="early_refusal", edge_confidence=0.7)
            for f in self.flow_nodes:
                self.g.add_edge(f, "F3_RETAIN", edge_type="retention_jump", guard_expr="mid_refusal", edge_confidence=0.8)
            for f in self.flow_nodes:
                self.g.add_edge("F3_RETAIN", f, edge_type="goto", guard_expr=f"resume_before:{f}", edge_confidence=0.65)
            self.g.add_edge("F3_RETAIN", "OBJ_FINAL", edge_type="goto", guard_expr="still_refuse", edge_confidence=0.6)
            self.g.add_edge("OBJ_FINAL", "END", edge_type="sequence", guard_expr="terminate", edge_confidence=1.0)

        # FAQ return rails
        for f in self.flow_nodes:
            self.g.add_edge("FAQ_NORMAL", f, edge_type="goto", guard_expr=f"resume_before:{f}", edge_confidence=0.65)
        self.g.add_edge("FAQ_OOB", "CLOSING", edge_type="goto", guard_expr="redirect_and_close", edge_confidence=0.7)

    def _attach_constraints(self) -> None:
        for c in self.instruction.constraints or []:
            self._add_node(c.id, "constraint", c.text, constraint_type=c.type.value)
            if c.type == ConstraintType.FLOW:
                self.g.add_edge(c.id, c.id, edge_type="covers_step", guard_expr="self", edge_confidence=1.0)
                continue
            if c.type == ConstraintType.KNOWLEDGE:
                self.g.add_edge(c.id, "FAQ_NORMAL", edge_type="on_user_ask", guard_expr="faq", edge_confidence=0.9)
            elif c.type == ConstraintType.BOUNDARY:
                self.g.add_edge(c.id, "FAQ_OOB", edge_type="applies_globally", guard_expr="always", edge_confidence=1.0)
            elif c.type == ConstraintType.DIALOGUE:
                self.g.add_edge(c.id, "CLOSING", edge_type="applies_globally", guard_expr="always", edge_confidence=1.0)

    def _attach_knowledge(self) -> None:
        for k in self.instruction.knowledge_nodes or []:
            if k.id not in self.g:
                self._add_node(k.id, "knowledge", k.text)
            attach_state = k.best_attach_state or "FAQ_NORMAL"
            if attach_state not in self.g:
                attach_state = "FAQ_NORMAL"
            self.g.add_edge(k.id, attach_state, edge_type="on_user_ask", guard_expr="knowledge_trigger", edge_confidence=0.85)
            self.attachment.setdefault(attach_state, []).append(k.id)

    def _attach_globals(self) -> None:
        self._add_node("GLOBAL_DIALOGUE", "meta", "GLOBAL_DIALOGUE")
        self._add_node("GLOBAL_BOUNDARY", "meta", "GLOBAL_BOUNDARY")
        for c in self.instruction.constraints or []:
            if c.type == ConstraintType.DIALOGUE:
                self.g.add_edge("GLOBAL_DIALOGUE", c.id, edge_type="global_guard", guard_expr="always", edge_confidence=1.0)
            if c.type == ConstraintType.BOUNDARY:
                self.g.add_edge("GLOBAL_BOUNDARY", c.id, edge_type="global_guard", guard_expr="always", edge_confidence=1.0)

    def detect_conflicts(self) -> List[ConflictItem]:
        out: List[ConflictItem] = []
        # duplicated dialogue limit
        dialog = [c for c in self.instruction.constraints if c.type == ConstraintType.DIALOGUE]
        seen: Dict[str, str] = {}
        for c in dialog:
            key = c.text.strip().lower()
            if key in seen:
                out.append(
                    ConflictItem(
                        conflict_id=f"dup_dialogue::{seen[key]}::{c.id}",
                        conflict_type="duplicate_dialogue_constraint",
                        description="Duplicate dialogue constraints found.",
                        node_ids=[seen[key], c.id],
                    )
                )
            else:
                seen[key] = c.id

        # flow/order consistency
        if len(self.flow_nodes) >= 2 and not self.g.has_edge(self.flow_nodes[0], self.flow_nodes[1]):
            out.append(
                ConflictItem(
                    conflict_id="missing_flow_sequence",
                    conflict_type="flow_sequence_break",
                    description="Flow graph misses basic sequence edge.",
                    node_ids=self.flow_nodes[:2],
                    severity="critical",
                )
            )
        return out

    def get_flow_nodes(self) -> List[str]:
        return ["START", *self.flow_nodes, "CLOSING", "END"]

    def get_rule_attachment(self) -> Dict[str, List[str]]:
        return dict(self.attachment)

    def has_retain_node(self) -> bool:
        return "F3_RETAIN" in self.g

    def has_oob_boundary(self) -> bool:
        return any(c.type == ConstraintType.BOUNDARY for c in self.instruction.constraints)

    def has_length_constraint(self) -> bool:
        return any(c.type == ConstraintType.DIALOGUE and "长度" in c.text for c in self.instruction.constraints)


def _attach_flow_branches_and_ops(G: nx.DiGraph, raw: str, flow_nodes: List[str]) -> None:
    """
    Attach structured conditional branches + op chains from raw instruction.
    When a step has branches, remove direct F_i→F_{i+1} sequence (must pick a branch).
    """
    if not raw or not flow_nodes:
        return

    flow_set = set(flow_nodes)
    structured = parse_instruction_branches(raw)
    steps_with_branches: set[int] = set()

    for br in structured:
        flow_node = f"F{br.step_no}"
        if flow_node not in flow_set:
            continue
        steps_with_branches.add(br.step_no)
        bid = br.branch_id
        label = f"若{br.condition}→{br.action}"
        if br.section:
            label = f"[{br.section}] {label}"
        if bid not in G:
            G.add_node(
                bid,
                node_type="flow_branch",
                step=br.step_no,
                index=br.branch_index,
                section=br.section,
                condition=br.condition,
                action=br.action,
                label=label,
                text=label,
            )
        if not G.has_edge(flow_node, bid):
            G.add_edge(flow_node, bid, edge_type="branch", guard_expr=br.condition)

        next_flow = f"F{br.step_no + 1}" if br.step_no + 1 <= len(flow_nodes) else None
        target = f"F{br.target_step}" if br.target_step and f"F{br.target_step}" in flow_set else None

        if br.op_steps:
            prev = bid
            for oi, op in enumerate(br.op_steps, start=1):
                oid = f"op::{br.step_no}::{br.branch_index}::{oi}"
                if oid not in G:
                    G.add_node(
                        oid,
                        node_type="op_step",
                        step=br.step_no,
                        branch_index=br.branch_index,
                        index=oi,
                        text=op,
                        label=op[:28],
                        pause_s=3,
                    )
                if not G.has_edge(prev, oid):
                    G.add_edge(prev, oid, edge_type="sequence", guard_expr="op_step")
                prev = oid
            exit_node = target or (next_flow if next_flow in flow_set else None)
            if exit_node and not G.has_edge(prev, exit_node):
                G.add_edge(prev, exit_node, edge_type="goto", guard_expr="branch_done")
        elif target and not G.has_edge(bid, target):
            G.add_edge(bid, target, edge_type="goto", guard_expr="branch_goto")
        elif next_flow and next_flow in flow_set and not G.has_edge(bid, next_flow):
            G.add_edge(bid, next_flow, edge_type="goto", guard_expr="branch_continue")

    # Legacy flat branches for steps not covered by structured parser
    for step_no, block in iter_step_blocks(raw):
        flow_node = f"F{step_no}"
        if flow_node not in flow_set or step_no in steps_with_branches:
            continue
        for b_i, (cond, act) in enumerate(extract_branches_from_block(block), start=1):
            bid = f"branch::{step_no}::{b_i}"
            if bid not in G:
                G.add_node(
                    bid,
                    node_type="flow_branch",
                    step=step_no,
                    index=b_i,
                    condition=cond,
                    action=act,
                    label=f"若{cond}→{act}",
                    text=f"若{cond}→{act}",
                )
            if not G.has_edge(flow_node, bid):
                G.add_edge(flow_node, bid, edge_type="branch")
            m2 = re.search(r"进入第\s*(\d+)\s*步", act)
            if m2:
                try:
                    t_step = int(m2.group(1))
                except ValueError:
                    t_step = None
                target = f"F{t_step}" if t_step else None
                if target and target in flow_set and not G.has_edge(bid, target):
                    G.add_edge(bid, target, edge_type="goto")
            next_flow = f"F{step_no + 1}"
            if next_flow in flow_set and not any(
                G.has_edge(bid, t) for t in flow_set if t.startswith("F") or t.startswith("op::")
            ):
                G.add_edge(bid, next_flow, edge_type="goto", guard_expr="branch_continue")

    # Remove direct sequence skip when step has mandatory branches
    for step_no in steps_with_branches:
        a, b = f"F{step_no}", f"F{step_no + 1}"
        if a in flow_set and b in flow_set and G.has_edge(a, b):
            G.remove_edge(a, b)
