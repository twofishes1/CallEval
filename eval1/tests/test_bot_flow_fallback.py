# -*- coding: utf-8 -*-
from eval1.layer2.instruction_injection import (
    _is_meta_step_line,
    compress_step_to_utterance,
    pick_flow_step_fallback,
)


def test_f3_fallback_avoids_continuous_days():
    line = pick_flow_step_fallback("F3", attempt=0)
    assert "连续" not in line
    assert "3天" not in line
    assert "安全" in line or "注意" in line or "加油" in line


def test_f3_meta_not_spoken_verbatim():
    step = "尽量挽留不想配送的骑手，鼓励能配送的骑手，并提醒他们注意安全。"
    assert _is_meta_step_line(step) or _is_meta_step_line("尽量挽留不想配送的骑手")
    line = compress_step_to_utterance(step, current_state="F3", max_len=30)
    assert "挽留不想配送的骑手" not in line
    assert "方便再听我说一句" not in line


def test_f3_fallback_is_retain_speech():
    line = pick_flow_step_fallback("F3", attempt=0)
    assert "挽留不想配送" not in line
    assert "安全" in line or "注意" in line or "加油" in line


def test_f3_retain_fallback_no_meta():
    line = pick_flow_step_fallback("F3_RETAIN", attempt=0)
    assert "挽留不想配送" not in line
    assert len(line) >= 6


def test_f2_single_utterance_not_split():
    step = "说明单日飞毛腿合同需要**连续 3 天**完成配送；否则合同将受到影响。"
    line = compress_step_to_utterance(step, current_state="F2", max_len=30)
    assert "连续" in line
    assert "影响" in line or "否则" in line
    assert line.count("。") <= 1
