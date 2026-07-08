"""内存桩实现 — 开发/测试用；生产环境配合 PostgresMiddleware + Redis 增强层。"""

from datetime import datetime, timezone
from typing import Any

from herness.middleware.beliefs import match_beliefs, resolve_belief_write_conflict
from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice
from herness.middleware.session import SessionHistoryEntry
from herness.models.worker import WorkerOutput
from herness.rag.models import RagSearchResult
from herness.rag.pipeline import RagPipeline
from herness.rag.store.memory import InMemoryKnowledgeStore


class InMemoryMiddleware:
    """基于 dict 的临时中台，演示权限边界与数据流。"""

    def __init__(self, *, hereness_enabled: bool = False, rag_enabled: bool = False) -> None:
        # 用户 → 预合成记忆
        self._memories: dict[str, PreSynthesizedMemory] = {}
        # 用户 → 信念库（Hereness 占位）
        self._beliefs: dict[str, list[dict[str, Any]]] = {}
        # 任务 → 已写入结果
        self._task_results: dict[str, WorkerOutput] = {}
        # 任务 → 元数据（含 session_id / input / final_answer）
        self._task_metadata: dict[str, dict[str, Any]] = {}
        # 任务 → 写入时间
        self._task_created_at: dict[str, datetime] = {}
        # Dreaming 队列（占位）
        self._dreaming_queue: list[tuple[str, str]] = []
        self._tool_policies: dict[tuple[str, str], list[str]] = {}
        self._hereness_enabled = hereness_enabled
        self._rag_enabled = rag_enabled
        self._belief_id_counter = 0
        self._conflict_decay_factor = 0.5
        self._superseded_threshold = 0.3
        self._kb_store = InMemoryKnowledgeStore()
        self._rag_pipeline: RagPipeline | None = None
        self._rag_settings: Any = None

    def configure_hereness_conflict(
        self,
        *,
        decay_factor: float = 0.5,
        superseded_threshold: float = 0.3,
    ) -> None:
        """配置 Hereness v3 冲突衰减参数（测试 / 工厂注入）。"""
        self._conflict_decay_factor = decay_factor
        self._superseded_threshold = superseded_threshold

    # ── 只读接口（Worker / Critic 可用）──

    async def get_task_context(self, user_id: str, task_id: str) -> dict[str, Any]:
        """返回任务级上下文，故意不包含全局记忆。"""
        return {
            "user_id": user_id,
            "task_id": task_id,
            "note": "任务级上下文（Worker 不可见全局记忆）",
        }

    async def query_beliefs(self, user_id: str, claims: list[str]) -> list[dict[str, Any]]:
        """从信念库检索与声明相关的条目。"""
        active = [
            b for b in self._beliefs.get(user_id, [])
            if b.get("status", "active") == "active"
        ]
        return match_beliefs(
            active,
            claims,
            deep=self._hereness_enabled,
        )

    def configure_rag(self, settings: Any, *, embedding_client: Any = None) -> None:
        """注入 RAG 配置与嵌入客户端（测试 / 工厂调用）。"""
        self._rag_settings = settings
        if settings.rag_enabled:
            self._rag_enabled = True
            self._rag_pipeline = RagPipeline(
                self._kb_store,
                settings,
                embedding_client=embedding_client,
            )

    @property
    def knowledge_store(self) -> InMemoryKnowledgeStore:
        return self._kb_store

    async def search_knowledge_base(
        self,
        query: str,
        *,
        collection_id: str = "default",
    ) -> RagSearchResult:
        if not self._rag_enabled or self._rag_pipeline is None:
            return RagSearchResult(query=query, collection_id=collection_id, hits=[])
        return await self._rag_pipeline.search(query, collection_id=collection_id)

    async def resolve_worker_tools(
        self,
        user_id: str,
        task_id: str,
    ) -> list[str] | None:
        """内存桩默认返回 None，沿用全局 Settings。"""
        return self._tool_policies.get((user_id, task_id))

    def set_tool_policy(self, user_id: str, task_id: str, tools: list[str]) -> None:
        """测试辅助：为中台设置任务级工具白名单。"""
        self._tool_policies[(user_id, task_id)] = tools

    # ── 读写接口（仅调度器/总管）──

    async def get_pre_synthesized_memory(self, user_id: str) -> PreSynthesizedMemory:
        """拉取预合成记忆；若不存在则返回空包。"""
        return self._memories.get(
            user_id,
            PreSynthesizedMemory(user_id=user_id, summary="（尚未生成记忆）"),
        )

    async def write_task_result(
        self,
        user_id: str,
        task_id: str,
        worker_output: WorkerOutput,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """写入已校验的任务结果。"""
        self._task_results[task_id] = worker_output
        if metadata:
            self._task_metadata[task_id] = dict(metadata)
        self._task_created_at.setdefault(task_id, datetime.now(timezone.utc))

    async def get_session_history(
        self,
        session_id: str,
        *,
        exclude_task_id: str | None = None,
        limit: int = 5,
        persona: str | None = None,
    ) -> list[SessionHistoryEntry]:
        """读取同 session 的前序任务摘要。"""
        entries: list[SessionHistoryEntry] = []
        for task_id, output in self._task_results.items():
            if exclude_task_id and task_id == exclude_task_id:
                continue
            meta = self._task_metadata.get(task_id, {})
            if meta.get("session_id") != session_id:
                continue
            if persona is not None and meta.get("persona") != persona:
                continue
            answer = meta.get("final_answer") or output.summary or output.content
            entries.append(
                SessionHistoryEntry(
                    task_id=task_id,
                    input=str(meta.get("input", "")),
                    answer=str(answer),
                    created_at=self._task_created_at.get(task_id),
                )
            )

        entries.sort(key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc))
        if limit > 0 and len(entries) > limit:
            entries = entries[-limit:]
        return entries

    async def enqueue_dreaming_job(self, user_id: str, task_id: str) -> None:
        """将任务加入 Dreaming 队列（占位，不实际执行）。"""
        self._dreaming_queue.append((user_id, task_id))

    async def get_task_result(self, user_id: str, task_id: str) -> WorkerOutput | None:
        """读取已持久化的任务结果，供 Dreaming 消费。"""
        output = self._task_results.get(task_id)
        if output is None:
            return None
        return output

    async def save_pre_synthesized_memory(self, memory: PreSynthesizedMemory) -> None:
        """写入或更新预合成记忆（Dreaming 合成后调用）。"""
        self._memories[memory.user_id] = memory

    async def dequeue_dreaming_job(self, *, timeout: int = 0) -> tuple[str, str] | None:
        """FIFO 出队；timeout>0 时在超时前轮询等待。"""
        import asyncio

        if self._dreaming_queue:
            return self._dreaming_queue.pop(0)
        if timeout <= 0:
            return None

        elapsed = 0.0
        poll = 0.05
        while elapsed < timeout:
            await asyncio.sleep(poll)
            elapsed += poll
            if self._dreaming_queue:
                return self._dreaming_queue.pop(0)
        return None

    async def mark_dreaming_job_done(
        self,
        user_id: str,
        task_id: str,
        *,
        success: bool = True,
    ) -> None:
        """内存桩无状态跟踪，仅保留接口兼容。"""

    # ── 测试辅助方法 ──

    def seed_memory(self, user_id: str, summary: str, slices: list[SynthesizedMemorySlice] | None = None) -> None:
        """预置用户记忆，便于本地调试。"""
        self._memories[user_id] = PreSynthesizedMemory(
            user_id=user_id,
            summary=summary,
            slices=slices or [],
        )

    def seed_belief(
        self,
        user_id: str,
        fact: str,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> None:
        """预置信念库条目；Hereness 启用时自动处理冲突衰减。"""
        existing = self._beliefs.get(user_id, [])
        adjusted = confidence
        status = "active"
        if self._hereness_enabled:
            adjusted, status, updates = resolve_belief_write_conflict(
                fact,
                confidence,
                existing,
                decay_factor=self._conflict_decay_factor,
                superseded_threshold=self._superseded_threshold,
            )
            for update in updates:
                for belief in existing:
                    if belief.get("id") != update.get("id"):
                        continue
                    if "confidence" in update:
                        belief["confidence"] = update["confidence"]
                    if "status" in update:
                        belief["status"] = update["status"]

        self._belief_id_counter += 1
        self._beliefs.setdefault(user_id, []).append(
            {
                "id": self._belief_id_counter,
                "fact": fact,
                "source": source,
                "confidence": adjusted,
                "status": status,
            }
        )

    @property
    def dreaming_queue(self) -> list[tuple[str, str]]:
        """查看 Dreaming 队列（调试用）。"""
        return list(self._dreaming_queue)
