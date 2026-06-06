# -*- coding: utf-8 -*-
from eval1.layer2.constraint_scenarios import (
    build_busy_brief_alts,
    build_driving_hangup_alts,
    is_driving_user,
    resolve_scenario_reply,
)


class _Kn:
    def __init__(self, id_, text):
        self.id = id_
        self.text = text


class _Constraint:
    def __init__(self, text):
        self.text = text


class _Inst:
    def __init__(self):
        self.constraints = [
            _Constraint("若商家说在开车，礼貌说「那我稍后再打」后挂断"),
            _Constraint("若老板说忙，说「就1分钟，保证简短」后继续简短说明"),
        ]
        self.knowledge_nodes = [
            _Kn("K12", "【我现在在开车】那我稍后再打"),
        ]


def test_is_driving_user():
    assert is_driving_user("我在开车，不太方便接电话。")
    assert not is_driving_user("我现在有点忙")


def test_driving_hangup_alts():
    alts = build_driving_hangup_alts(_Inst())
    assert any("稍后再打" in a for a in alts)


def test_busy_brief_alts():
    alts = build_busy_brief_alts(_Inst())
    assert any("1分钟" in a for a in alts)


def test_resolve_driving_force_end():
    inst = _Inst()
    reply = resolve_scenario_reply(
        inst,
        last_user_utterance="我在开车，不太方便。",
        bot_state={},
        current_state="CLOSING",
        path_nodes=["PROBE_D10_DRIVE", "CLOSING"],
    )
    assert reply is not None
    assert reply.force_end
    assert "稍后再打" in reply.text


def test_resolve_busy_brief_once():
    inst = _Inst()
    reply = resolve_scenario_reply(
        inst,
        last_user_utterance="我现在有点忙，能简短点吗？",
        bot_state={},
        current_state="F2",
        path_nodes=["PROBE_D9_BUSY"],
    )
    assert reply is not None
    assert reply.mark_busy_briefed
    assert "1分钟" in reply.text

    reply2 = resolve_scenario_reply(
        inst,
        last_user_utterance="还是很忙",
        bot_state={"busy_briefed": True},
        current_state="F2",
        path_nodes=[],
    )
    assert reply2 is None
