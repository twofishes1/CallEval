"""Bot constraint violations must use message turn index, not round*2."""

from eval1.layer2.dst import DST


def test_bot_violation_turn_matches_message_turn():
    """Regression: turn_index must equal bot message turn (e.g. T19), not turn_count*2 (T20)."""
    dst = DST()
    long_bot = "理解等通知的难处！名额靠接单保，明天能上线就稳住排名～注意安全！"
    assert len(long_bot.replace(" ", "")) > 30

    bot_message_turn = 19
    violations = dst.check_constraints(
        long_bot,
        turn_index=bot_message_turn,
        instruction=None,
        fsm=None,  # type: ignore[arg-type]
    )
    assert len(violations) == 1
    assert violations[0]["turn_index"] == 19
    assert violations[0]["violation_type"] == "dialogue_length"
