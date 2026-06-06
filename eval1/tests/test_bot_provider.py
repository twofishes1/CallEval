from eval1.bot_provider import (
    bot_provider_scope,
    get_bot_llm_profile,
    list_available_report_providers,
    normalize_bot_provider,
    reports_output_path,
)


def test_reports_output_path_suffix():
    assert reports_output_path("instruction_1", "qwen").name == "eval1_reports_instruction_1.json"
    assert reports_output_path("instruction_1", "deepseek").name == "eval1_reports_instruction_1_deepseek.json"


def test_normalize_bot_provider():
    assert normalize_bot_provider("deepseek") == "deepseek"
    assert normalize_bot_provider("QWEN") == "qwen"


def test_get_bot_llm_profile_deepseek():
    with bot_provider_scope("deepseek"):
        prof = get_bot_llm_profile()
    assert prof["bot_provider"] == "deepseek"
    assert "deepseek" in prof["api_base"].lower() or prof["api_base"]


def test_list_available_report_providers_structure():
    rows = list_available_report_providers("instruction_1")
    assert len(rows) == 2
    assert {r["bot_provider"] for r in rows} == {"qwen", "deepseek"}
