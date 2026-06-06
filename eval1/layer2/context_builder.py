from __future__ import annotations

from typing import List

from eval1.layer2.goal_fsm import GoalFSM


class ContextBuilder:
    def build(
        self,
        fsm: GoalFSM,
        last_bot_utterance: str,
        covered_nodes: List[str],
        turn_index: int,
        *,
        rider_name: str = "",
    ) -> str:
        remaining = [n for n in fsm.path_nodes[fsm.pointer:] if n not in {"START"}]
        who = f"user_identity={rider_name}; " if rider_name else ""
        return (
            f"turn={turn_index}; {who}"
            f"current_state={fsm.current_state}; pointer={fsm.pointer}; "
            f"required_action={fsm.get_required_action_for_path()}; "
            f"allowed_user_actions={','.join(fsm.get_allowed_user_actions())}; "
            f"covered_nodes={','.join(covered_nodes[-6:])}; "
            f"remaining_nodes={','.join(remaining[:6])}; "
            f"last_bot={last_bot_utterance}"
        )
