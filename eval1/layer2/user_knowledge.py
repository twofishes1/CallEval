from __future__ import annotations

from typing import List

from eval1.layer2.action_detector import split_knowledge_snippets
from eval1.layer2.user_context_memory import UserContextMemory, merge_bot_knowledge


async def extract_new_knowledge(bot_utterance: str, user_memory: List[str]) -> List[str]:
    """Extract new facts from bot reply and return prefixed memory entries."""
    mem = UserContextMemory.from_legacy(user_memory)
    known = set(mem.bot_facts)
    snippets = split_knowledge_snippets(bot_utterance)
    new_items: List[str] = []
    for s in snippets:
        if s in known:
            continue
        if any(s[:8] == k[:8] for k in known if len(k) >= 8 and len(s) >= 8):
            continue
        new_items.append(s)
        known.add(s)
    if not new_items:
        return list(user_memory or [])
    return merge_bot_knowledge(mem, new_items)
