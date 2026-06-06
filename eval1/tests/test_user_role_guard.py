# -*- coding: utf-8 -*-
from eval1.layer2.user_role_guard import (
    caller_role_leak_reason,
    is_caller_role_leak,
    is_stale_identity_ack,
    stale_identity_ack_reason,
    user_facing_task_summary,
)


def test_stale_identity_ack():
    bot = "好的，我们对直播产品做了升级，新增了低延迟直播。"
    assert is_stale_identity_ack("对，您说。", last_bot=bot, current_state="F2")
    assert stale_identity_ack_reason("对，您说。", last_bot=bot, current_state="F2")


def test_not_stale_at_opening():
    assert not is_stale_identity_ack(
        "是的，我是。",
        last_bot="您好，请问您是负责人吗？",
        current_state="START",
    )
    opening = "您好，请问您是贵培训机构/校区的负责人吗？"
    leak = "等等，我们对直播产品做了升级，新增了独立的低延迟直播"
    assert is_caller_role_leak(leak, last_bot=opening, current_state="START")
    assert caller_role_leak_reason(leak, last_bot=opening, current_state="START")


def test_not_leak_after_bot_announced_upgrade():
    bot = "好的，我们对直播产品做了升级，新增了低延迟直播选项。"
    user = "明白了，这个升级挺好的。"
    assert not is_caller_role_leak(user, last_bot=bot, current_state="F2", bot_history=[bot])


def test_user_facing_task_summary_not_bot_script():
    summary = user_facing_task_summary(("education_live",), "培训机构/校区负责人")
    assert "告知机构" not in summary
    assert "低延迟" not in summary
    assert "等对方说明" in summary
