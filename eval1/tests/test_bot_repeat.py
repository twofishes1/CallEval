from eval1.layer2.simulation_graph import SimulationGraph


def test_is_repetitive_catches_f3_theme_paraphrase():
    sim = SimulationGraph()
    history = [
        "注意安全，祝你配送顺利！",
        "好的，注意安全，祝你配送顺利！",
    ]
    candidate = "配送时注意安全，有单尽量接！"
    assert sim._is_repetitive(candidate, history, current_state="F3")
