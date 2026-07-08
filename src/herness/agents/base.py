"""LLM 模型工厂 — 支持本地 vLLM 与云端 API（OpenAI / OpenAI 兼容 / Anthropic）。"""

from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from herness.config import Settings


def _is_dashscope_endpoint(base_url: str) -> bool:
    return "dashscope.aliyuncs.com" in base_url.lower()


def _is_qwen_hybrid_model(model: str) -> bool:
    """可切换 thinking 的 Qwen 混合模型（默认开启 thinking，需显式关闭）。"""
    name = model.lower()
    if "thinking" in name or name.startswith("qwq"):
        return False
    return name.startswith("qwen")


def resolve_enable_thinking(settings: Settings) -> bool | None:
    """解析是否向模型传递 enable_thinking；None 表示不干预 provider 默认行为。"""
    if settings.llm_enable_thinking is not None:
        return settings.llm_enable_thinking
    if _is_dashscope_endpoint(settings.llm_base_url) and _is_qwen_hybrid_model(settings.llm_model):
        # Qwen3.7 等在 DashScope 上默认开启 thinking，与 pydantic-ai 结构化输出的
        # tool_choice=required 不兼容，需显式关闭。
        return False
    return None


def build_model_settings(
    settings: Settings,
    *,
    temperature: float | None = None,
) -> ModelSettings | None:
    """根据配置与采样温度构建 ModelSettings。"""
    kwargs: dict[str, object] = {}
    if temperature is not None:
        kwargs["temperature"] = temperature

    enable_thinking = resolve_enable_thinking(settings)
    if enable_thinking is not None:
        kwargs["thinking"] = enable_thinking
        kwargs["extra_body"] = {"enable_thinking": enable_thinking}

    return ModelSettings(**kwargs) if kwargs else None


def build_model(settings: Settings, *, temperature: float | None = None):
    """根据配置构建 LLM 模型实例。

    切换后端只需改 .env，代码无需改动：
    - 本地 vLLM：LLM_PROVIDER=openai_compatible + LLM_BASE_URL=http://localhost:8000/v1
    - OpenAI 官方：LLM_PROVIDER=openai + LLM_API_KEY=sk-... + LLM_MODEL=gpt-4o
    - DeepSeek 等：LLM_PROVIDER=openai_compatible + LLM_BASE_URL=https://api.deepseek.com/v1
    - 阿里百炼：DASHSCOPE_API_KEY=sk-... + LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 + LLM_MODEL=qwen3.7-max
    - Claude 官方：LLM_PROVIDER=anthropic + LLM_API_KEY=sk-ant-... + LLM_MODEL=claude-sonnet-4-6
    """
    model_settings = build_model_settings(settings, temperature=temperature)
    api_key = settings.llm_api_key or None  # None 时 Provider 会读环境变量

    if settings.llm_provider == "anthropic":
        provider = AnthropicProvider(api_key=api_key) if api_key else AnthropicProvider()
        return AnthropicModel(
            settings.llm_model,
            provider=provider,
            settings=model_settings,
        )

    if settings.llm_provider == "openai":
        # OpenAI 官方：base_url 留空则走 api.openai.com
        if settings.llm_base_url and not settings.llm_base_url.startswith("http://localhost"):
            provider = OpenAIProvider(base_url=settings.llm_base_url, api_key=api_key)
        else:
            provider = OpenAIProvider(api_key=api_key) if api_key else OpenAIProvider()
        return OpenAIChatModel(
            settings.llm_model,
            provider=provider,
            settings=model_settings,
        )

    # openai_compatible：vLLM、DeepSeek、Moonshot、智谱、通义等 OpenAI 兼容 API
    provider = OpenAIProvider(
        base_url=settings.llm_base_url,
        api_key=api_key or "dummy",  # 本地 vLLM 可填 dummy；云端 API 必须填真实 Key
    )
    return OpenAIChatModel(
        settings.llm_model,
        provider=provider,
        settings=model_settings,
    )
