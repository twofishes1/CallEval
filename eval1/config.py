from pathlib import Path
from typing import Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Always load eval1/.env regardless of process cwd.
        env_file=str(Path(__file__).resolve().parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM — 用户模拟 / 评委（Qwen DashScope）
    dashscope_api_key: str = ""
    qwen_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model_fast: str = "qwen-plus"
    llm_model_main: str = "qwen-plus"
    llm_model_judge: str = "qwen-turbo"

    # 被测 Bot — DeepSeek（OpenAI 兼容）
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_bot_model: str = "deepseek-chat"
    llm_temperature_parse: float = 0.1
    llm_temperature_sim: float = 0.7

    # 对话控制
    max_turns_absolute: int = 30
    default_max_turns: int = 20  # spec 4.6 默认上限
    min_turns_buffer: int = 4
    turn_buffer_ratio: float = 0.5
    turns_per_path_node: int = 2

    # Persona 附加轮次
    persona_turn_extra: Dict[str, int] = Field(
        default_factory=lambda: {
            "resistant": 4,
            "questioning": 3,
            "ignorant": 3,
            "impatient": 0,
            "cooperative": 0,
            "off_topic": 2,
        }
    )

    # 节点轮次成本
    node_turn_cost: Dict[str, int] = Field(
        default_factory=lambda: {
            "flow_step": 2,
            "OBJECTION": 4,
            "F3_RETAIN": 3,
            "FAQ_NORMAL": 3,
            "FAQ_OOB": 2,
            "CLOSING": 1,
        }
    )

    # 评分权重（单 Judge + 规则分，权重之和 = 1.0）
    weight_rule: float = 0.40
    weight_llm: float = 0.60
    judge_temperature: float = 0.10

    # 动作检测
    action_llm_fallback: bool = False

    # 并发
    max_concurrent_dialogues: int = 4
    llm_max_concurrent: int = 8
    llm_robust_max_retry: int = 2
    llm_request_timeout_sec: float = 45.0
    llm_dialogue_timeout_sec: float = 28.0
    plan_timeout_sec: float = 900.0

    # 重试
    path_verify_max_retry: int = 3
    action_verify_max_retry: int = 3


settings = Settings()
