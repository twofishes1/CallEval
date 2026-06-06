# -*- coding: utf-8 -*-
"""F4 must not repeat full explanation after user acknowledges."""
from eval1.layer2.instruction_injection import (
    F4_DEFAULT_CLAUSES,
    advance_f4_speech_index,
    build_f4_single_utterance,
    f4_coverage_summary,
    pick_f4_next_utterance,
    pick_f4_post_ack,
    sync_f4_completion,
)

STEP4 = "".join(f"{c}。" for c in F4_DEFAULT_CLAUSES)


def test_sync_f4_from_bot_history_marks_complete():
    line = build_f4_single_utterance(STEP4)
    state: dict = {}
    sync_f4_completion(state, [line])
    assert f4_coverage_summary(state).get("complete") is True


def test_pick_f4_empty_after_delivery():
    state: dict = {"f4_speech_index": 0}
    first = pick_f4_next_utterance(state, STEP4)
    advance_f4_speech_index(state)
    second = pick_f4_next_utterance(state, STEP4)
    assert first == build_f4_single_utterance(STEP4)
    assert second == ""


def test_post_ack_differs_from_full_f4():
    line = build_f4_single_utterance(STEP4)
    ack = pick_f4_post_ack([line], attempt=0)
    assert ack != line
    assert "再见" in ack
