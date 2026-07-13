"""运行时指标 — 进程内计数器，供 /metrics 与运维排查。"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from herness.models.task import TaskStatus


@dataclass
class MetricsRegistry:
    """线程安全的进程内指标注册表。"""

    tasks_by_status: dict[str, int] = field(default_factory=dict)
    critic_rejections_total: int = 0
    step_retries_total: int = 0
    step_retries_by_name: dict[str, int] = field(default_factory=dict)
    rounds_count: int = 0
    rounds_sum: int = 0
    rounds_max: int = 0
    duration_count: int = 0
    duration_sum_seconds: float = 0.0
    dreaming_jobs_completed: int = 0
    dreaming_jobs_failed: int = 0
    token_input_total: int = 0
    token_output_total: int = 0
    token_requests_total: int = 0
    tokens_by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record_task_finished(
        self,
        status: TaskStatus,
        *,
        rounds: int,
        duration_seconds: float,
    ) -> None:
        with self._lock:
            key = status.value
            self.tasks_by_status[key] = self.tasks_by_status.get(key, 0) + 1
            self.rounds_count += 1
            self.rounds_sum += rounds
            self.rounds_max = max(self.rounds_max, rounds)
            self.duration_count += 1
            self.duration_sum_seconds += duration_seconds

    def record_critic_rejection(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.critic_rejections_total += count

    def record_step_retry(self, step_name: str) -> None:
        with self._lock:
            self.step_retries_total += 1
            self.step_retries_by_name[step_name] = (
                self.step_retries_by_name.get(step_name, 0) + 1
            )

    def record_dreaming_job(self, *, success: bool) -> None:
        with self._lock:
            if success:
                self.dreaming_jobs_completed += 1
            else:
                self.dreaming_jobs_failed += 1

    def record_token_usage(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        requests: int = 0,
        source: str = "orchestrator",
    ) -> None:
        if input_tokens <= 0 and output_tokens <= 0 and requests <= 0:
            return
        with self._lock:
            self.token_input_total += max(input_tokens, 0)
            self.token_output_total += max(output_tokens, 0)
            self.token_requests_total += max(requests, 0)
            bucket = self.tokens_by_source.setdefault(
                source,
                {"input_total": 0, "output_total": 0, "requests_total": 0},
            )
            bucket["input_total"] += max(input_tokens, 0)
            bucket["output_total"] += max(output_tokens, 0)
            bucket["requests_total"] += max(requests, 0)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            duration_avg = (
                self.duration_sum_seconds / self.duration_count
                if self.duration_count
                else 0.0
            )
            rounds_avg = self.rounds_sum / self.rounds_count if self.rounds_count else 0.0
            return {
                "tasks_total": dict(self.tasks_by_status),
                "critic_rejections_total": self.critic_rejections_total,
                "step_retries_total": self.step_retries_total,
                "step_retries_by_name": dict(self.step_retries_by_name),
                "rounds": {
                    "count": self.rounds_count,
                    "sum": self.rounds_sum,
                    "max": self.rounds_max,
                    "avg": round(rounds_avg, 2),
                },
                "task_duration_seconds": {
                    "count": self.duration_count,
                    "sum": round(self.duration_sum_seconds, 3),
                    "avg": round(duration_avg, 3),
                },
                "dreaming_jobs": {
                    "completed": self.dreaming_jobs_completed,
                    "failed": self.dreaming_jobs_failed,
                },
                "tokens": {
                    "input_total": self.token_input_total,
                    "output_total": self.token_output_total,
                    "total": self.token_input_total + self.token_output_total,
                    "requests_total": self.token_requests_total,
                    "by_source": dict(self.tokens_by_source),
                },
            }


_registry: MetricsRegistry | None = None


def get_metrics_registry() -> MetricsRegistry:
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
    return _registry


def reset_metrics_registry() -> MetricsRegistry:
    """重置全局指标（测试用）。"""
    global _registry
    _registry = MetricsRegistry()
    return _registry
