"""应用配置 — 通过环境变量或 .env 文件注入，后续接入真实数据库与模型密钥。"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 支持的 LLM 后端类型
LlmProvider = Literal[
    "openai_compatible",  # OpenAI 兼容格式（vLLM / DeepSeek /  Moonshot / 智谱 等）
    "openai",             # OpenAI 官方 API
    "anthropic",          # Anthropic Claude 官方 API
]


class Settings(BaseSettings):
    """全局配置项，所有敏感信息留空占位，由部署时填入。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM 后端（本地 vLLM 或云端 API 均在此配置）──
    llm_provider: LlmProvider = Field(
        default="openai_compatible",
        description="模型后端：openai_compatible | openai | anthropic",
    )
    llm_base_url: str = Field(
        default="http://localhost:8000/v1",
        description="API 地址；openai_compatible 必填；openai/anthropic 可留空用官方默认",
    )
    llm_api_key: str = Field(
        default="",
        description="API Key；留空时可读对应厂商环境变量（OPENAI_API_KEY 等）",
    )
    llm_model: str = Field(
        default="default",
        description="模型名称，如 gpt-4o / deepseek-chat / claude-sonnet-4-6",
    )

    # 兼容旧配置名（vLLM 时代），会自动映射到 llm_* 字段
    vllm_base_url: str = Field(default="", validation_alias="VLLM_BASE_URL")
    vllm_api_key: str = Field(default="", validation_alias="VLLM_API_KEY")
    model_name: str = Field(default="", validation_alias="MODEL_NAME")

    # ── 各 Agent 采样温度 ──
    supervisor_temperature: float = 0.0  # 总管：确定性规划
    worker_temperature: float = 0.3      # 执行：略有余地
    critic_temperature: float = 0.0      # 校验：严格一致

    # ── 调度器防护参数 ──
    max_rounds: int = Field(default=8, ge=1, le=50, description="单任务最大轮数")
    step_timeout_seconds: float = Field(default=120.0, gt=0, description="单步超时（秒）")
    task_timeout_seconds: float = Field(default=600.0, gt=0, description="整任务超时（秒）")
    max_retries_per_step: int = Field(default=2, ge=0, le=10, description="单步最大重试次数")

    # ── 数据库占位（后续接入 Postgres + Redis）──
    postgres_dsn: str = Field(default="", description="PostgreSQL 连接串")
    redis_url: str = Field(default="", description="Redis 连接地址")

    # ── 离线管线占位（Dreaming + Hereness）──
    dreaming_enabled: bool = False   # 异步事实提炼
    hereness_enabled: bool = False   # 信念库冲突消歧

    def model_post_init(self, __context: object) -> None:
        """兼容旧 env 变量名：VLLM_* / MODEL_NAME 优先覆盖 llm_*。"""
        if self.vllm_base_url:
            object.__setattr__(self, "llm_base_url", self.vllm_base_url)
        if self.vllm_api_key:
            object.__setattr__(self, "llm_api_key", self.vllm_api_key)
        if self.model_name:
            object.__setattr__(self, "llm_model", self.model_name)


def get_settings() -> Settings:
    """读取并返回配置单例（每次调用重新解析环境变量）。"""
    return Settings()
