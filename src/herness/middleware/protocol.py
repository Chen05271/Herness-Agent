"""中台协议 — 定义读写边界，Worker/Critic 只能访问只读接口。"""

from typing import Any, Literal, Protocol, runtime_checkable

from herness.middleware.memory import PreSynthesizedMemory
from herness.middleware.session import SessionHistoryEntry
from herness.models.worker import WorkerOutput

PersonaFilter = Literal["consumer", "merchant"]


@runtime_checkable
class ReadOnlyMiddleware(Protocol):
    """只读中台 API — 暴露给 Worker 与 Critic。"""

    async def get_task_context(self, user_id: str, task_id: str) -> dict[str, Any]:
        """获取任务级上下文（不含全局记忆）。"""
        ...

    async def query_beliefs(self, user_id: str, claims: list[str]) -> list[dict[str, Any]]:
        """查询 Hereness 信念库，用于事实一致性校验。"""
        ...

    async def resolve_worker_tools(
        self,
        user_id: str,
        task_id: str,
    ) -> list[str] | None:
        """返回允许的工具逻辑名列表；None 表示沿用全局 Settings。"""
        ...

    async def search_knowledge_base(
        self,
        query: str,
        *,
        collection_id: str = "default",
    ) -> Any:
        """RAG 知识库检索，返回 RagSearchResult 或等价 dict。"""
        ...


@runtime_checkable
class DataMiddleware(ReadOnlyMiddleware, Protocol):
    """完整中台 API — 仅调度器/总管可调用。"""

    async def get_pre_synthesized_memory(self, user_id: str) -> PreSynthesizedMemory:
        """拉取离线预合成的全局记忆，注入总管。"""
        ...

    async def write_task_result(
        self,
        user_id: str,
        task_id: str,
        worker_output: WorkerOutput,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """持久化已校验的任务结果，供下游 Dreaming 管线消费。"""
        ...

    async def enqueue_dreaming_job(self, user_id: str, task_id: str) -> None:
        """投递 Dreaming 异步任务（离线事实提炼），在线链路不阻塞。"""
        ...

    async def get_session_history(
        self,
        session_id: str,
        *,
        exclude_task_id: str | None = None,
        limit: int = 5,
        persona: PersonaFilter | None = None,
    ) -> list[SessionHistoryEntry]:
        """读取同 session 的前序任务摘要（不含当前 task_id）。"""
        ...
