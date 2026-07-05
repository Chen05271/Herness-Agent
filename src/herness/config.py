"""应用配置 — 通过环境变量或 .env 文件注入，后续接入真实数据库与模型密钥。"""

from functools import lru_cache
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
    max_retries_per_step: int = Field(
        default=2,
        ge=0,
        le=10,
        description=(
            "单步最大重试次数。"
            "Agent 层（PydanticAI retries）处理 LLM 结构化输出格式错误；"
            "调度器层（Orchestrator）处理网络/超时等瞬时错误。"
        ),
    )
    max_parallel_workers: int = Field(
        default=4, ge=1, le=20, description="单轮并行 Worker 上限"
    )
    session_history_limit: int = Field(
        default=5, ge=0, le=50, description="Supervisor 注入的同 session 前序任务条数上限"
    )

    # ── HTTP API ──
    api_host: str = Field(default="0.0.0.0", description="API 监听地址")
    api_port: int = Field(default=8080, ge=1, le=65535, description="API 监听端口")
    api_key: str = Field(
        default="",
        description="API Key；留空则不鉴权（开发模式）",
    )
    rate_limit_per_user: int = Field(
        default=0,
        ge=0,
        le=10_000,
        description="每 user_id 在窗口内的最大任务提交数；0 表示不限",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=86400,
        description="rate limit 滑动窗口长度（秒）",
    )

    # ── 数据库（Postgres 持久化 + Redis 缓存/队列）──
    postgres_dsn: str = Field(default="", description="PostgreSQL 连接串")
    redis_url: str = Field(default="", description="Redis 连接地址")
    redis_memory_ttl_seconds: int = Field(
        default=3600, ge=60, description="预合成记忆 Redis 缓存 TTL（秒）"
    )
    redis_task_ttl_seconds: int = Field(
        default=86400, ge=300, description="API 任务状态 Redis TTL（秒）"
    )

    # ── 离线管线（Dreaming + Hereness）──
    dreaming_enabled: bool = False   # 异步事实提炼
    dreaming_temperature: float = Field(
        default=0.2, ge=0.0, le=2.0, description="Dreaming 记忆合成温度"
    )
    dreaming_poll_timeout_seconds: int = Field(
        default=5, ge=0, le=300, description="Dreaming 队列阻塞出队超时（秒）"
    )
    dreaming_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="单条 Dreaming 任务失败后的最大重试次数",
    )
    dreaming_retry_backoff_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=60.0,
        description="Dreaming 重试间隔基数（秒），按 attempt 线性递增",
    )
    hereness_enabled: bool = Field(
        default=False,
        description="Hereness 信念库深度校验（全文检索 + 矛盾检测）",
    )
    hereness_vector_enabled: bool = Field(
        default=False,
        description="Hereness v2 向量语义检索（需 pgvector + Embeddings API）",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embeddings 模型名称",
    )
    embedding_dimensions: int = Field(
        default=1536,
        ge=1,
        le=4096,
        description="向量维度（须与 beliefs.fact_embedding 列一致）",
    )
    embedding_base_url: str = Field(
        default="",
        description="Embeddings API 地址；留空则沿用 LLM_BASE_URL",
    )
    embedding_api_key: str = Field(
        default="",
        description="Embeddings API Key；留空则沿用 LLM_API_KEY",
    )
    hereness_vector_top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="向量检索返回条数上限",
    )
    hereness_vector_min_similarity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="向量相似度阈值（余弦相似度，1 为完全相同）",
    )
    hereness_conflict_decay_factor: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Hereness v3 矛盾信念置信度衰减系数",
    )
    hereness_superseded_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Hereness v3 置信度低于此值的信念标记为 superseded",
    )

    # ── 可观测性 ──
    structured_logging: bool = Field(
        default=False,
        description="启用 JSON 行日志（log_event 输出不再带传统前缀）",
    )
    metrics_enabled: bool = Field(
        default=True,
        description="是否采集运行时指标（/metrics 端点）",
    )

    # ── 智慧农业电商 BFF（mock / HTTP 可切换）──
    agri_commerce_enabled: bool = Field(
        default=False,
        description="启用农业电商只读工具（get_order / trace_batch 等）",
    )
    agri_commerce_mode: Literal["mock", "http"] = Field(
        default="mock",
        description="mock=本地样例数据；http=对接 AGRI_COMMERCE_BASE_URL",
    )
    agri_commerce_base_url: str = Field(
        default="",
        description="电商 BFF 根地址，如 http://localhost:9000/v1",
    )
    agri_commerce_api_key: str = Field(
        default="",
        description="BFF 服务 Token（Bearer）",
    )
    agri_commerce_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=120.0,
        description="BFF HTTP 超时（秒）",
    )

    # ── Worker 外部工具 ──
    worker_tools_http_enabled: bool = Field(
        default=True,
        description="Worker 是否可使用 http_request 工具",
    )
    worker_tools_http_max_bytes: int = Field(
        default=65536,
        ge=1024,
        le=1_048_576,
        description="HTTP 响应体最大字节数",
    )
    worker_tools_file_enabled: bool = Field(
        default=False,
        description="Worker 是否可使用 read_text_file 工具",
    )
    worker_tools_file_base_dir: str = Field(
        default="",
        description="文件工具允许读取的根目录；留空则禁用文件工具",
    )
    worker_tools_file_max_bytes: int = Field(
        default=65536,
        ge=1024,
        le=1_048_576,
        description="单文件最大读取字节数",
    )
    worker_tools_code_enabled: bool = Field(
        default=False,
        description="Worker 是否可使用 run_python_code 工具（生产环境谨慎开启）",
    )
    worker_tools_code_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=120.0,
        description="Python 代码执行超时（秒）",
    )

    def model_post_init(self, __context: object) -> None:
        """兼容旧 env 变量名：VLLM_* / MODEL_NAME 优先覆盖 llm_*。"""
        if self.vllm_base_url:
            object.__setattr__(self, "llm_base_url", self.vllm_base_url)
        if self.vllm_api_key:
            object.__setattr__(self, "llm_api_key", self.vllm_api_key)
        if self.model_name:
            object.__setattr__(self, "llm_model", self.model_name)


@lru_cache
def get_settings() -> Settings:
    """读取并返回配置单例（进程内缓存，环境变量变更后需 clear_settings_cache）。"""
    return Settings()


def clear_settings_cache() -> None:
    """清除配置缓存（测试或热重载时使用）。"""
    get_settings.cache_clear()
