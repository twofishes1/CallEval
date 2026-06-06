# -*- coding: utf-8 -*-
from eval1.layer2.instruction_injection import (
    F4_COMPRESSED_LINE,
    F4_PART_META,
    advance_f4_speech_index,
    build_f4_single_utterance,
    build_f4_utterance_parts,
    compress_f4_step_to_utterance,
    f4_coverage_summary,
    f4_parts_remaining,
    pick_f4_next_utterance,
    pick_flow_step_utterance,
    update_f4_delivery,
    _char_len,
)

STEP4 = (
    "说明飞毛腿报名是按排名进行的，并非站长干预。"
    "骑手应减少拒单、取消和超时。在恶劣天气下工作、订单量更高，有助于保住飞毛腿资格。"
)


def test_f4_single_utterance_matches_flow_step():
    line = build_f4_single_utterance(STEP4)
    assert "排名" in line and "站长" in line
    assert "拒单" in line and "取消" in line and "超时" in line
    assert "恶劣天气" in line or "天气" in line
    assert "资格" in line
    assert line.count("。") >= 3


def test_f4_compress_prefers_full_line():
    line = compress_f4_step_to_utterance(STEP4, max_len=0)
    assert line == build_f4_single_utterance(STEP4)


def test_f4_pick_delivers_once_then_stops():
    state: dict = {"f4_speech_index": 0}
    first = pick_f4_next_utterance(state, STEP4)
    advance_f4_speech_index(state)
    second = pick_f4_next_utterance(state, STEP4)
    assert first
    assert second == ""
    assert first == build_f4_single_utterance(STEP4)


def test_f4_coverage_complete_after_one_turn():
    state: dict = {"f4_speech_index": 0}
    line = pick_f4_next_utterance(state, STEP4)
    update_f4_delivery(state, line)
    advance_f4_speech_index(state)
    cov = f4_coverage_summary(state)
    assert cov["complete"] is True
    assert set(cov["delivered"]) == {k for k, _ in F4_PART_META}


def test_f4_parts_remaining_one_shot():
    state: dict = {"f4_speech_index": 0}
    assert f4_parts_remaining(state) == 1
    advance_f4_speech_index(state)
    assert f4_parts_remaining(state) == 0


def test_f4_pick_from_instruction_step():
    state: dict = {"f4_speech_index": 0}
    line = pick_flow_step_utterance("F4", STEP4, state)
    assert line == build_f4_single_utterance(STEP4)


def test_f4_coverage_from_compressed_line():
    state: dict = {"f4_speech_index": 0}
    update_f4_delivery(state, F4_COMPRESSED_LINE)
    cov = f4_coverage_summary(state)
    assert cov["complete"] is True
    assert set(cov["delivered"]) == {"ranking", "reject", "weather"}


def test_f4_build_three_parts_still_available_for_short_clauses():
    parts = build_f4_utterance_parts(STEP4)
    assert len(parts) == 3
    assert all(_char_len(p) <= 30 for p in parts)
