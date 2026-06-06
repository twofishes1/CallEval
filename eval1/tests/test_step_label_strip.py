# -*- coding: utf-8 -*-
from eval1.layer2.instruction_injection import compress_step_to_utterance, sanitize_bot_output, _strip_step_label
from eval1.layer2.bot_wrapper import BotWrapper


def test_strip_step_label():
    assert _strip_step_label("Step5: 检查学员端费用。") == "检查学员端费用。"
    assert _strip_step_label("Step 7: 结束通话。") == "结束通话。"


def test_compress_does_not_keep_step_prefix():
    line = compress_step_to_utterance("Step5: 检查学员端费用/加速线路费（如有使用）。")
    assert "Step" not in line
    assert "检查" in line


def test_sanitize_bot_output_strips_any_step():
    assert sanitize_bot_output("好的，Step3 请确认是否知情。") == "好的，请确认是否知情。"
    assert sanitize_bot_output("step2告知升级内容") == "告知升级内容"
    assert "step" not in sanitize_bot_output("Step1: 身份确认").lower()


def test_is_bad_response_rejects_any_step_label():
    bot = BotWrapper()
    assert bot._is_bad_response("Step5 检查费用")
    assert bot._is_bad_response("好的 step3 继续")
    assert not bot._is_bad_response("好的，请确认是否知情。")
