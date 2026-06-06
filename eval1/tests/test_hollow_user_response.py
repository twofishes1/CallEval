from eval1.layer2.persona import PERSONA_REGISTRY, PersonaType
from eval1.layer2.persona_phrasing import is_hollow_user_response


def test_hollow_rejects_single_char_for_questioning():
    p = PERSONA_REGISTRY[PersonaType.QUESTIONING]
    assert is_hollow_user_response("好。", p)
    assert is_hollow_user_response("嗯", p)
    assert not is_hollow_user_response("这个排名依据是什么？", p)


def test_hollow_allows_impatient_short():
    p = PERSONA_REGISTRY[PersonaType.IMPATIENT]
    assert not is_hollow_user_response("行。", p)


def test_hollow_rejects_bare_mingbai_for_resistant():
    p = PERSONA_REGISTRY[PersonaType.RESISTANT]
    assert is_hollow_user_response("明白。", p)
