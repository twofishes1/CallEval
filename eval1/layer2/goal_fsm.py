from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

FLOW_NODES = {"CLOSING"}
INTERRUPTION_NODES = {"OBJECTION", "F3_RETAIN", "FAQ_NORMAL", "FAQ_OOB", "OBJ_FINAL"}
_RETAIN_ENTRY_NODES = frozenset({"F3_RETAIN", "OBJECTION"})
# Only treat path coverage as a rule violation below this rate (aligns with rule_judge).
FLOW_COVERAGE_VIOLATION_THRESHOLD = 0.85


def _is_flow_step(node: str) -> bool:
    if node in INTERRUPTION_NODES:
        return False
    return node.startswith("F") or node in FLOW_NODES


def parse_bot_action_steps(bot_action_log: List[str] | None) -> Set[str]:
    """Extract FSM step ids from bot_action_log entries like T3:step_response:F2."""
    steps: Set[str] = set()
    for entry in bot_action_log or []:
        text = str(entry)
        if not text:
            continue
        if "opening_line" in text:
            steps.add("OPENING")
        if ":" in text:
            step = text.rsplit(":", 1)[-1].strip()
            if step:
                steps.add(step)
    return steps


def merge_effective_coverage(
    path_nodes: List[str],
    covered_nodes: List[str],
    bot_action_log: List[str] | None = None,
) -> Set[str]:
    """Union FSM visited nodes with bot delivery log (FSM alone under-counts)."""
    visited = {str(n) for n in (covered_nodes or []) if n}
    visited |= parse_bot_action_steps(bot_action_log)
    if "OPENING" in visited and "F1" in path_nodes:
        visited.add("F1")
    if "CLOSING" in visited or "END" in visited:
        visited.add("CLOSING")
    return visited


def get_applicable_path_nodes(path_nodes: List[str], visited: Set[str]) -> List[str]:
    """Required nodes for this trajectory; skip FAQ/挽留 branches never entered."""
    core = [x for x in path_nodes if x not in {"START", "END"}]
    if not core:
        return []
    applicable: List[str] = []
    for node in core:
        if node in INTERRUPTION_NODES:
            if node in visited:
                applicable.append(node)
            continue
        applicable.append(node)
    return applicable


@dataclass
class PathTransitionResult:
    moved: bool
    from_state: str
    to_state: str
    reason: str = ""


@dataclass
class GoalFSM:
    """FSM driven by Layer1 enumerated path — pointer walks path_nodes in order."""

    path_nodes: List[str]
    pointer: int = 0
    current_state: str = "START"
    # legacy stack kept for compatibility; path mode prefers pointer jumps
    stack: List[tuple[str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path_nodes:
            self.pointer = max(0, min(self.pointer, len(self.path_nodes) - 1))
            self.current_state = self.path_nodes[self.pointer]

    @classmethod
    def from_path(cls, path_nodes: List[str]) -> "GoalFSM":
        nodes = list(path_nodes or ["START", "END"])
        return cls(path_nodes=nodes, pointer=0, current_state=nodes[0] if nodes else "START")

    def is_terminal(self) -> bool:
        return self.current_state == "END"

    def go_to_final(self) -> None:
        if "END" in self.path_nodes:
            self.pointer = self.path_nodes.index("END")
        else:
            self.pointer = max(0, len(self.path_nodes) - 1)
        self.current_state = "END"

    def go_to_node(self, node: str, *, reason: str = "") -> PathTransitionResult:
        prev = self.current_state
        if node not in self.path_nodes:
            return PathTransitionResult(False, prev, prev, reason="node_not_on_path")
        self.pointer = self.path_nodes.index(node)
        self.current_state = node
        return PathTransitionResult(True, prev, node, reason=reason)

    def _find_ahead(self, candidates: Set[str], start: int | None = None) -> Optional[int]:
        i0 = (start if start is not None else self.pointer + 1)
        for i in range(i0, len(self.path_nodes)):
            if self.path_nodes[i] in candidates:
                return i
        return None

    def _next_main_flow_index(self, start: int | None = None) -> Optional[int]:
        i0 = (start if start is not None else self.pointer + 1)
        for i in range(i0, len(self.path_nodes)):
            if _is_flow_step(self.path_nodes[i]) or self.path_nodes[i] == "END":
                return i
        return None

    def _next_comply_target(self, start: int) -> Optional[int]:
        """Next path index reachable via comply (skips retention / final-only nodes)."""
        for i in range(start, len(self.path_nodes)):
            n = self.path_nodes[i]
            if n in _RETAIN_ENTRY_NODES or n == "OBJ_FINAL" or n == "END":
                continue
            if _is_flow_step(n) or n in {"FAQ_NORMAL", "FAQ_OOB", "CLOSING"}:
                return i
        return None

    def try_transition(
        self,
        user_action: str,
        *,
        retain_success: bool = False,
        consecutive_reject: int = 0,
        reject_limit: int = 3,
    ) -> PathTransitionResult:
        """Move along enumerated path according to user action."""
        prev = self.current_state
        if self.is_terminal():
            return PathTransitionResult(False, prev, prev, reason="terminal")

        action = str(user_action or "comply")

        # Hard terminate on path — only after retention/objection, not from F1 first reject
        if (
            consecutive_reject >= reject_limit
            and "OBJ_FINAL" in self.path_nodes
            and self.current_state in {"F3_RETAIN", "OBJECTION", "OBJ_FINAL"}
        ):
            return self.go_to_node("OBJ_FINAL", reason="reject_limit") if self.current_state != "OBJ_FINAL" else PathTransitionResult(False, prev, prev)

        if action == "hangup":
            return self.go_to_node("END", reason="hangup")

        if action in {"ask_question", "off_topic"}:
            target = "FAQ_OOB" if action == "off_topic" else "FAQ_NORMAL"
            idx = self._find_ahead({target})
            if idx is not None:
                self.pointer = idx
                self.current_state = self.path_nodes[idx]
                return PathTransitionResult(True, prev, self.current_state, reason=action)
            return PathTransitionResult(False, prev, prev, reason="faq_not_on_path")

        if action == "reject":
            idx = self._find_ahead({"OBJECTION", "F3_RETAIN"})
            if idx is not None:
                self.pointer = idx
                self.current_state = self.path_nodes[idx]
                return PathTransitionResult(True, prev, self.current_state, reason="reject")
            return PathTransitionResult(False, prev, prev, reason="reject_not_on_path")

        # comply / confirm / retain success
        if action in {"comply", "confirm"} or retain_success:
            if self.current_state in {"OBJECTION", "F3_RETAIN"} or retain_success:
                idx = self._next_main_flow_index()
            elif self.current_state in {"FAQ_NORMAL", "FAQ_OOB"}:
                idx = self._next_main_flow_index()
            else:
                idx = self.pointer + 1 if self.pointer + 1 < len(self.path_nodes) else None
                if idx is not None and self.path_nodes[idx] in _RETAIN_ENTRY_NODES:
                    idx = self._next_comply_target(idx)
                    if idx is None:
                        return PathTransitionResult(False, prev, prev, reason="comply_hold_before_reject")
                elif idx is not None and self.path_nodes[idx] in INTERRUPTION_NODES:
                    idx = self._next_main_flow_index()

            if idx is None:
                return PathTransitionResult(False, prev, prev, reason="no_next")
            self.pointer = idx
            self.current_state = self.path_nodes[idx]
            return PathTransitionResult(True, prev, self.current_state, reason="comply")

        return PathTransitionResult(False, prev, prev, reason="unknown_action")

    def advance(self) -> None:
        """Sequential advance (legacy helper). Prefer try_transition."""
        if self.pointer < len(self.path_nodes) - 1:
            self.pointer += 1
            self.current_state = self.path_nodes[self.pointer]
        else:
            self.current_state = "END"

    def interrupt(self, state: str) -> None:
        self.stack.append((self.current_state, self.pointer))
        if state in self.path_nodes:
            self.pointer = self.path_nodes.index(state)
        self.current_state = state

    def resume(self) -> None:
        if self.stack:
            s, p = self.stack.pop()
            self.current_state = s
            self.pointer = p

    def get_step_index(self, node_id: str) -> int:
        try:
            return self.path_nodes.index(node_id)
        except ValueError:
            return -1

    def planned_next_nodes(self, limit: int = 4) -> List[str]:
        return [n for n in self.path_nodes[self.pointer + 1 : self.pointer + 1 + limit]]

    def path_has_node(self, node: str) -> bool:
        return node in self.path_nodes

    def get_required_action_for_path(self) -> str:
        if self.is_terminal():
            return "terminate"
        if self.current_state in {"OBJECTION", "F3_RETAIN", "OBJ_FINAL"}:
            return "resolve_objection"
        if self.current_state in {"FAQ_NORMAL", "FAQ_OOB"}:
            return "answer_question"
        if self.current_state == "CLOSING":
            return "close_dialogue"
        return "advance_flow"

    def get_allowed_user_actions(self) -> List[str]:
        if self.is_terminal():
            return ["hangup"]
        if self.current_state == "CLOSING":
            return ["confirm", "hangup", "ask_question"]
        if self.current_state in {"OBJECTION", "F3_RETAIN"}:
            return ["reject", "ask_question", "comply"]
        allowed = ["comply", "ask_question", "reject", "off_topic"]
        if not any(self.path_has_node(n) for n in {"OBJECTION", "F3_RETAIN"}):
            allowed = [a for a in allowed if a != "reject"]
        return allowed

    def is_goal_achieved(self) -> bool:
        """Goal complete when FSM has reached END on the enumerated path."""
        if not self.is_terminal():
            return False
        return bool(self.path_nodes) and self.path_nodes[-1] == "END"

    def should_go_to_final(self) -> bool:
        if self.current_state == "OBJ_FINAL":
            return True
        return self.current_state == "END" or (
            self.pointer >= len(self.path_nodes) - 1 and self.current_state in {"CLOSING", "END"}
        )

    def get_flow_adherence_rate(
        self,
        covered_nodes: List[str],
        bot_action_log: List[str] | None = None,
    ) -> float:
        visited = merge_effective_coverage(self.path_nodes, covered_nodes, bot_action_log)
        applicable = get_applicable_path_nodes(self.path_nodes, visited)
        if not applicable:
            return 1.0
        hit = sum(1 for n in applicable if n in visited)
        return hit / len(applicable)
