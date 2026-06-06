from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConstraintType(str, Enum):
    ROLE = "role"
    FLOW = "flow"
    DIALOGUE = "dialogue"
    KNOWLEDGE = "knowledge"
    BOUNDARY = "boundary"
    VARIABLE = "variable"


class Constraint(BaseModel):
    id: str
    type: ConstraintType
    text: str
    priority: int = 3
    is_hard: bool = False
    measurable: bool = False
    detection_rule: str = ""


class KnowledgeNode(BaseModel):
    id: str
    text: str
    trigger_type: str
    trigger_keywords: List[str] = []
    variables: List[str] = []
    precondition_nodes: List[str] = []
    best_attach_state: str = "FAQ_NORMAL"


class VariableNode(BaseModel):
    name: str
    value: str
    locations: List[str] = []
    semantic: str = ""


class ParsedInstruction(BaseModel):
    instruction_id: str
    raw_text: str
    resolved_text: str = ""
    role_description: str
    task_description: str
    opening_line: str
    flow_steps: List[str]
    constraints: List[Constraint]
    knowledge_nodes: List[KnowledgeNode]
    variables: Dict[str, VariableNode]
    has_conflicts: bool = False
    resolved: bool = False


class ConflictRecord(BaseModel):
    conflict_id: str
    constraint_ids: List[str]
    conflict_type: str
    description: str
    severity: str
    suggested_fix: str = ""
    auto_fixable: bool = False


class RepairResult(BaseModel):
    conflict_id: str
    fix_type: str
    target_id: str
    attribute_changes: Dict[str, Any] = {}
    modified_text: str = ""
    detection_rule_update: str = ""
    rationale: str


class FlowNodeType(str, Enum):
    FLOW_STEP = "flow_step"
    TRANSITION = "transition"
    META = "meta"


class FlowNode(BaseModel):
    node_id: str
    node_type: FlowNodeType
    label: str
    step_index: Optional[int] = None


class FSMTransition(BaseModel):
    from_node: str
    to_node: str
    trigger_type: str
    label: str


class EnumeratedPath(BaseModel):
    path_id: str
    nodes: List[str]
    activated_rules: List[str]
    base_max_turns: int
    description: str
    flow_description: str = ""
    rules_description: str = ""
    category_label: str = ""
    branch_notes: str = ""
    target_knowledge_id: str = ""
    knowledge_target_label: str = ""
    target_scenario_id: str = ""
    scenario_target_label: str = ""
    path_sequence_display: str = ""
    node_labels: Dict[str, str] = Field(default_factory=dict)
    rule_labels: Dict[str, str] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    plan_id: str
    path: EnumeratedPath
    persona_type: str
    tone_modifier: str = "default"
    variable_values: Dict[str, str]
    repeat_count: int = 1
    max_turns: int
    reason: str = ""
    # semantic_match | potential_contradiction | control_contradictory (legacy reports)
    plan_group: str = "semantic_match"


class ViolationEvidence(BaseModel):
    turn_index: int
    violation_type: str
    constraint_id: str
    constraint_text: str
    bot_utterance: str
    explanation: str
    deduction: float


class EvalReport(BaseModel):
    report_id: str
    plan_id: str
    path_id: str
    persona_type: str
    total_score: float
    grade: str
    rule_score: float
    llm_score: float
    consistency_penalty: float
    consistency_alert: bool = False
    consistency_kappa: float = 1.0
    consistency_note: str = ""
    flow_adherence_rate: float
    total_turns: int
    termination_reason: str
    violations: List[ViolationEvidence]
    dimension_scores: Dict[str, float]
    score_breakdown: str = ""
    judge_comment: str = ""
    top_improvement: str = ""
    dimension_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str
    improvement_suggestions: List[str]
    created_at: str
