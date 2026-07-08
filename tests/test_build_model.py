"""LLM 模型工厂与 thinking 配置测试。"""

from herness.agents.base import build_model_settings, resolve_enable_thinking
from herness.config import Settings


def test_dashscope_qwen_defaults_thinking_off() -> None:
    settings = Settings(
        llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        llm_model="qwen3.7-max",
    )
    assert resolve_enable_thinking(settings) is False


def test_dashscope_qwen_respects_explicit_thinking_on() -> None:
    settings = Settings(
        llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        llm_model="qwen3.7-max",
        llm_enable_thinking=True,
    )
    assert resolve_enable_thinking(settings) is True


def test_non_qwen_models_do_not_auto_disable_thinking() -> None:
    settings = Settings(
        llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        llm_model="deepseek-chat",
    )
    assert resolve_enable_thinking(settings) is None


def test_build_model_settings_injects_extra_body_for_qwen() -> None:
    settings = Settings(
        llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        llm_model="qwen3.7-max",
        worker_temperature=0.3,
    )
    model_settings = build_model_settings(settings, temperature=settings.worker_temperature)
    assert model_settings is not None
    assert model_settings["temperature"] == 0.3
    assert model_settings["thinking"] is False
    assert model_settings["extra_body"] == {"enable_thinking": False}
