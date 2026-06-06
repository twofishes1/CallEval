from eval1.report.recalc_coverage import recalc_flow_adherence, recalc_one


def test_recalc_flow_improves_faq_skip():
    dialogue = {
        "path_nodes": ["START", "F1", "FAQ_NORMAL", "F2", "F3", "F4", "CLOSING", "END"],
        "bot_state_log": [
            {"current_step_id": "START"},
            {"current_step_id": "F1"},
            {"current_step_id": "F2"},
            {"current_step_id": "F3"},
            {"current_step_id": "F4"},
            {"current_step_id": "CLOSING"},
        ],
        "bot_state": {
            "bot_action_log": [
                "T1:opening_line:START",
                "T2:step_response:F1",
                "T3:step_response:F2",
                "T4:step_response:F3",
                "T5:f4_part:F4",
                "T6:step_response:CLOSING",
            ]
        },
    }
    assert recalc_flow_adherence(dialogue) == 1.0


def test_recalc_drops_flow_miss_when_above_threshold():
    report = {
        "report_id": "t1",
        "path_id": "P10",
        "llm_score": 88.0,
        "violations": [
            {
                "violation_type": "flow_miss",
                "constraint_id": "P10",
                "deduction": 2.86,
                "turn_index": 1,
            }
        ],
        "flow_adherence_rate": 0.857,
    }
    dialogue = {
        "path_nodes": ["START", "F1", "F2", "FAQ_NORMAL", "F3", "F4", "CLOSING", "END"],
        "bot_state_log": [
            {"current_step_id": "F1"},
            {"current_step_id": "F2"},
            {"current_step_id": "F3"},
            {"current_step_id": "F4"},
            {"current_step_id": "CLOSING"},
        ],
        "bot_state": {
            "bot_action_log": [
                "T1:opening_line:START",
                "T2:step_response:F1",
                "T3:step_response:F2",
                "T4:step_response:F3",
                "T5:f4_part:F4",
                "T6:step_response:CLOSING",
            ]
        },
        "opening_line_match": True,
        "repetitive_bot_count": 0,
        "messages": [{"role": "bot"}, {"role": "user"}] * 6,
    }
    out = recalc_one(report, dialogue)
    assert out["flow_adherence_rate"] == 1.0
    assert not any(v.get("violation_type") == "flow_miss" for v in out["violations"])
