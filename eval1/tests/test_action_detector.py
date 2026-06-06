import pytest

from eval1.layer2.action_detector import detect_actual_action, is_retain_success
from eval1.layer2.user_knowledge import extract_new_knowledge


def test_detect_reject_not_want_sign():
    assert detect_actual_action("是我，但我不太想签这个") == "reject"


def test_detect_reject_harsh_rule():
    assert detect_actual_action("能跑，但连续三天太苛刻") == "reject"


def test_detect_acknowledgment_as_comply():
    from eval1.layer2.action_detector import ActionDetector, looks_like_acknowledgment

    assert looks_like_acknowledgment("谢谢站长，我会尽量多接单的")
    det = ActionDetector()
    r = det.detect_sync("谢谢站长，我会尽量多接单的", default="")
    assert r.action == "comply"
    assert r.source == "acknowledgment"


def test_detect_retain_success():
    assert is_retain_success("三天？行吧，我试试") is True


def test_detect_retain_not_success_when_still_rejecting():
    assert is_retain_success("这规定谁定的？不太合理") is False


@pytest.mark.asyncio
async def test_extract_new_knowledge_dedupes():
    mem = ["fact:今天飞毛腿合同已生效"]
    out = await extract_new_knowledge("今天飞毛腿合同已生效，能开始配送吗？", mem)
    assert sum(1 for x in out if "飞毛腿合同已生效" in x) == 1
    out2 = await extract_new_knowledge("排名按拒单率计算。", mem)
    assert any("排名" in x for x in out2)
