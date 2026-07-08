"""数据中台层 — 协议定义、内存桩与 Postgres 持久化实现。

请从子模块直接导入（如 ``herness.middleware.factory``），勿在本包 ``__init__`` 中
eager import，否则会与 ``herness.redis.cache`` 形成循环依赖。
"""

__all__ = [
    "DataMiddleware",
    "InMemoryMiddleware",
    "PostgresMiddleware",
    "PreSynthesizedMemory",
    "ReadOnlyMiddleware",
    "RedisAugmentedMiddleware",
    "SynthesizedMemorySlice",
    "close_middleware",
    "create_middleware",
]
