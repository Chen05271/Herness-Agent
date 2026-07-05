"""任务实时消息中心 — 供 SSE 流式推送审计日志。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

from herness.models.task import TaskMessage, TaskStatus

MessageListener = Callable[[TaskMessage], None]
_TERMINAL = object()


class TaskLiveHub:
    """进程内任务消息广播：运行中追加、终态通知订阅者。"""

    def __init__(self) -> None:
        self._messages: dict[str, list[TaskMessage]] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._terminal: dict[str, TaskStatus] = {}
        self._lock = asyncio.Lock()

    async def start_task(self, task_id: str) -> None:
        async with self._lock:
            self._messages[task_id] = []
            self._queues[task_id] = []
            self._terminal.pop(task_id, None)

    def publish(self, task_id: str, message: TaskMessage) -> None:
        """同步发布（供调度器 _log 调用）。"""
        messages = self._messages.get(task_id)
        if messages is None:
            return
        messages.append(message)
        for queue in self._queues.get(task_id, []):
            queue.put_nowait(message)

    async def finish_task(self, task_id: str, status: TaskStatus) -> None:
        async with self._lock:
            self._terminal[task_id] = status
            for queue in self._queues.get(task_id, []):
                queue.put_nowait(_TERMINAL)

    async def messages(self, task_id: str) -> list[TaskMessage]:
        async with self._lock:
            return list(self._messages.get(task_id, []))

    async def stream(self, task_id: str, *, after: int = 0) -> AsyncIterator[TaskMessage]:
        """从 after 索引起推送新消息，任务终态后结束。"""
        async with self._lock:
            if task_id not in self._messages:
                return
            history = self._messages[task_id]
            for msg in history[after:]:
                yield msg
            after = len(history)
            if task_id in self._terminal:
                return
            queue: asyncio.Queue = asyncio.Queue()
            self._queues.setdefault(task_id, []).append(queue)

        try:
            while True:
                item = await queue.get()
                if item is _TERMINAL:
                    break
                yield item
        finally:
            async with self._lock:
                subs = self._queues.get(task_id, [])
                if queue in subs:
                    subs.remove(queue)

    def make_listener(self, task_id: str) -> MessageListener:
        """为调度器构造 on_message 回调。"""

        def _listener(message: TaskMessage) -> None:
            self.publish(task_id, message)

        return _listener
