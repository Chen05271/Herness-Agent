"""LLM 模型工厂 — 支持本地 vLLM 与云端 API（OpenAI / OpenAI 兼容 / Anthropic）。"""

from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from herness.config import Settings


def build_model(settings: Settings, *, temperature: float | None = None):
    """根据配置构建 LLM 模型实例。

    切换后端只需改 .env，代码无需改动：
    - 本地 vLLM：LLM_PROVIDER=openai_compatible + LLM_BASE_URL=http://localhost:8000/v1
    - OpenAI 官方：LLM_PROVIDER=openai + LLM_API_KEY=sk-... + LLM_MODEL=gpt-4o
    - DeepSeek 等：LLM_PROVIDER=openai_compatible + LLM_BASE_URL=https://api.deepseek.com/v1
    - Claude 官方：LLM_PROVIDER=anthropic + LLM_API_KEY=sk-ant-... + LLM_MODEL=claude-sonnet-4-6
    """
    model_settings = ModelSettings(temperature=temperature) if temperature is not None else None
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
