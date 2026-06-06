from __future__ import annotations

from typing import Optional, Tuple

from eval1.layer2.state import DialogueState

_USER_HANGUP_MARKERS = ("挂了", "再见", "先这样")
_BOT_HANGUP_MARKERS = ("再见", "感谢您的来电", "谢谢您的来电", "祝您", "先这样", "不打扰了")


class TerminationChecker:
    """Termination policy per spec 4.6 priority order."""

    def check(self, state: DialogueState) -> Tuple[bool, Optional[str]]:
        # hard_violation > hangup > goal_achieved > user_refused > max_turns
        if bool(state.get("hard_violation")):
            return True, "hard_violation"

        messages = state.get("messages") or []
        if messages:
            last = messages[-1]
            role = str(last.get("role", "")).lower()
            content = str(last.get("content", ""))
            if role == "user" and any(k in content for k in _USER_HANGUP_MARKERS):
                return True, "hangup"
            if role == "bot" and any(k in content for k in _BOT_HANGUP_MARKERS):
                return True, "hangup"

        if bool(state.get("should_terminate")):
            return True, str(state.get("termination_reason") or "hangup")

        reason = str(state.get("termination_reason") or "")
        if reason in {"goal_achieved", "user_refused", "hangup"}:
            return True, reason

        if int(state.get("turn_count") or 0) >= int(state.get("max_turns") or 0):
            return True, "max_turns"

        return False, None
