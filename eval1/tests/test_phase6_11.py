import asyncio

from eval1.layer1.models import EnumeratedPath, ExecutionPlan
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.simulation_graph import SimulationGraph
from eval1.layer3.aggregator import Aggregator


def test_termination_priority_hard_violation():
    sg = SimulationGraph()
    out = sg._termination_priority(  # noqa: SLF001 - intentional whitebox check
        hard_violation=True,
        user_action="hangup",
        goal_achieved=True,
        user_refused=True,
        max_turns=True,
    )
    assert out == "hard_violation"


def test_aggregator_hard_fail_zero():
    a = Aggregator().aggregate(90, 90, 0, hard_fail=True)
    assert a["total_score"] == 0.0
    assert a["grade"] == "F"


def test_path_coverage_verification_true():
    path = EnumeratedPath(
        path_id="P1",
        nodes=["START", "F1", "F2", "CLOSING", "END"],
        activated_rules=[],
        base_max_turns=8,
        description="x",
    )
    plan = ExecutionPlan(
        plan_id="P1:cooperative",
        path=path,
        persona_type="cooperative",
        variable_values={},
        max_turns=8,
    )
    persona = PERSONA_REGISTRY[PersonaType.COOPERATIVE]
    sg = SimulationGraph()

    class _FakeUser:
        async def generate(self, *_args, **_kwargs):
            return {
                "utterance": "可以继续",
                "action": "comply",
                "forced_retries": 0,
                "llm_connected": False,
            }

    class _FakeBot:
        async def reply(self, *_args, **_kwargs):
            return {"text": "好的，继续流程。", "llm_connected": False}

    sg.user_sim = _FakeUser()
    sg.bot = _FakeBot()
    ret = asyncio.run(sg.run_dialogue(plan, persona))
    assert "termination_reason" in ret
    assert isinstance(ret.get("path_covered"), bool)
