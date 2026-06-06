from eval1.layer2.bot_repeat_guard import (
    is_busy_or_refuse_user,
    is_semantically_repetitive,
    pick_non_repeating,
)
from eval1.layer2.simulation_graph import SimulationGraph


def test_semantic_repeat_contact_phrases():
    history = ["那您先忙，有需要再联系我。"]
    assert is_semantically_repetitive("理解，有事再联系。", history)
    assert is_semantically_repetitive("有需要再联系我。", history)


def test_busy_user_detected():
    assert is_busy_or_refuse_user("没空，别找我。")
    assert is_busy_or_refuse_user("忙呢，别说了。")


def test_pick_non_repeating_avoids_contact_closing():
    history = ["有需要再联系我。"]
    out = pick_non_repeating(
        ["有需要再联系我。", "理解，您先忙，这边先不打扰了。"],
        history,
    )
    assert "再联系" not in out


def test_is_repetitive_uses_semantic_guard():
    sim = SimulationGraph()
    history = ["那您先忙，有需要再联系我。"]
    assert sim._is_repetitive("好的，有事再联系。", history)
