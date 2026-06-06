import pytest

from eval1.layer2.dst import DST


@pytest.mark.asyncio
async def test_should_advance_when_user_acknowledges_step():
    dst = DST()
    ok = await dst.should_advance_after_user_comply(
        last_user_utterance="知道了，我会连续三天准时配送。",
        last_bot_utterance="单日合同需连续3天配送，否则影响派单哦！",
        expected_step_text="说明单日合同需连续3天配送，否则影响后续派单。",
    )
    assert ok is True


def test_user_acknowledged():
    assert DST().user_acknowledged("好的，我明白了。") is True
    assert DST().user_acknowledged("这规定谁定的？") is False


def test_opening_line_exempt_from_length_limit():
    dst = DST()
    long_opening = "你好，请问是张伟吗？我是站长。我看到你已报名飞毛腿。请记住，午餐和晚餐高峰期需要上线。单日合同每天至少完成5单；多日合同每天至少完成3单。"
    assert len(long_opening.replace(" ", "")) > 30
    out = dst.check_constraints(
        long_opening,
        turn_index=2,
        instruction=None,
        fsm=None,  # type: ignore[arg-type]
        is_opening_line=True,
    )
    assert not any(v.get("violation_type") == "dialogue_length" for v in out)

    out2 = dst.check_constraints(
        long_opening,
        turn_index=4,
        instruction=None,
        fsm=None,  # type: ignore[arg-type]
        is_opening_line=False,
    )
    assert any(v.get("violation_type") == "dialogue_length" for v in out2)
