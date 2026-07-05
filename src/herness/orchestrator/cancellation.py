"""任务取消注册表 — 供 API 与调度器协作中断 RUNNING 任务。"""

from __future__ import annotations

import asyncio
from threading import Lock


class TaskCancelledError(Exception):
    """任务被用户或 API 主动取消。"""


class TaskCancellationRegistry:
    """进程内任务取消信号（按 task_id）。"""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._pre_cancelled: set[str] = set()
        self._lock = Lock()

    def register(self, task_id: str) -> None:
        with self._lock:
            self._pre_cancelled.discard(task_id)
            self._events[task_id] = asyncio.Event()

    def unregister(self, task_id: str) -> None:
        with self._lock:
            self._events.pop(task_id, None)
            self._pre_cancelled.discard(task_id)

    def request_cancel(self, task_id: str) -> None:
        """请求取消（PENDING 或 RUNNING）。"""
        with self._lock:
            self._pre_cancelled.add(task_id)
            event = self._events.get(task_id)
        if event is not None:
            event.set()

    def cancel(self, task_id: str) -> bool:
        """请求取消；返回 False 表示 task_id 从未登记。"""
        with self._lock:
            known = task_id in self._events or task_id in self._pre_cancelled
        if not known:
            return False
        self.request_cancel(task_id)
        return True

    def is_cancelled(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._pre_cancelled:
                return True
            event = self._events.get(task_id)
        return event is not None and event.is_set()

    def mark_pending(self, task_id: str) -> None:
        """登记 PENDING 任务，便于启动前取消。"""
        with self._lock:
            self._pre_cancelled.discard(task_id)

    def is_pre_cancelled(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._pre_cancelled

    def get_event(self, task_id: str) -> asyncio.Event | None:
        with self._lock:
            return self._events.get(task_id)
