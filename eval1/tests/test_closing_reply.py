from eval1.layer2.instruction_grounding import (
    build_closing_reply_alts,
    infer_closing_tone,
    is_bad_closing_response,
)


def test_cooperative_closing_tone():
    tone = infer_closing_tone(
        last_user_utterance="好。",
        user_action="comply",
        consecutive_reject=0,
        dialogue_history=[
            {"role": "user", "content": "明白了，我会按时完成任务。"},
            {"role": "bot", "content": "坚持送3天，才能保住资格，加油！"},
            {"role": "user", "content": "好。"},
        ],
    )
    assert tone == "cooperative"
    alts = build_closing_reply_alts(None, tone)
    assert "理解您的难处" not in alts[0]
    assert "再见" in alts[0]


def test_refused_closing_uses_sympathy_hangup():
    tone = infer_closing_tone(
        last_user_utterance="真的跑不了，别打了。",
        user_action="reject",
        consecutive_reject=3,
        covered_nodes=["F3", "F3_RETAIN"],
    )
    assert tone in {"refused", "busy", "neutral"}
    alts = build_closing_reply_alts(None, "refused")
    assert any("难处" in a or "不打扰" in a for a in alts)


def test_bad_closing_rejects_faq_leak_and_sympathy_on_cooperative():
    assert is_bad_closing_response("目前，许多骑手正在申请飞毛腿。", "cooperative")
    assert is_bad_closing_response("理解您的难处，先不打扰了，再见。", "cooperative")
    assert not is_bad_closing_response("好的，祝您配送顺利，再见。", "cooperative")
