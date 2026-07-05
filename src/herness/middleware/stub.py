"""内存桩实现 — 开发/测试用，后续替换为 PostgresMiddleware + RedisCache。"""

from typing import Any

from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice
from herness.models.worker import WorkerOutput


class InMemoryMiddleware:
    """基于 dict 的临时中台，演示权限边界与数据流。"""

    def __init__(self) -> None:
        # 用户 → 预合成记忆
        self._memories: dict[str, PreSynthesizedMemory] = {}
        # 用户 → 信念库（Hereness 占位）
        self._beliefs: dict[str, list[dict[str, Any]]] = {}
        # 任务 → 已写入结果
        self._task_results: dict[str, WorkerOutput] = {}
        # Dreaming 队列（占位）
        self._dreaming_queue: list[tuple[str, str]] = []

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
        user_beliefs = self._beliefs.get(user_id, [])
        results: list[dict[str, Any]] = []
        for claim in claims:
            matched = [
                b for b in user_beliefs
                if claim.lower() in b.get("fact", "").lower()
            ]
            if matched:
                results.append({"claim": claim, "status": "supported", "matches": matched})
            else:
                results.append({"claim": claim, "status": "unknown", "matches": []})
        return results

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

    async def enqueue_dreaming_job(self, user_id: str, task_id: str) -> None:
        """将任务加入 Dreaming 队列（占位，不实际执行）。"""
        self._dreaming_queue.append((user_id, task_id))

    # ── 测试辅助方法 ──

    def seed_memory(self, user_id: str, summary: str, slices: list[SynthesizedMemorySlice] | None = None) -> None:
        """预置用户记忆，便于本地调试。"""
        self._memories[user_id] = PreSynthesizedMemory(
            user_id=user_id,
            summary=summary,
            slices=slices or [],
        )

    def seed_belief(self, user_id: str, fact: str, source: str = "manual") -> None:
        """预置信念库条目。"""
        self._beliefs.setdefault(user_id, []).append({"fact": fact, "source": source})

    @property
    def dreaming_queue(self) -> list[tuple[str, str]]:
        """查看 Dreaming 队列（调试用）。"""
        return list(self._dreaming_queue)
