"""运行时指标测试。"""

from herness.models.task import TaskStatus
from herness.observability.metrics import MetricsRegistry, reset_metrics_registry


def test_record_task_finished() -> None:
    registry = reset_metrics_registry()
    registry.record_task_finished(TaskStatus.COMPLETED, rounds=3, duration_seconds=12.5)
    registry.record_task_finished(TaskStatus.FAILED, rounds=1, duration_seconds=2.0)

    snapshot = registry.snapshot()
    assert snapshot["tasks_total"]["completed"] == 1
    assert snapshot["tasks_total"]["failed"] == 1
    assert snapshot["rounds"]["count"] == 2
    assert snapshot["rounds"]["sum"] == 4
    assert snapshot["rounds"]["max"] == 3
    assert snapshot["task_duration_seconds"]["count"] == 2


def test_record_critic_and_retries() -> None:
    registry = MetricsRegistry()
    registry.record_critic_rejection(2)
    registry.record_step_retry("Supervisor")
    registry.record_step_retry("Supervisor")
    registry.record_step_retry("Critic")

    snapshot = registry.snapshot()
    assert snapshot["critic_rejections_total"] == 2
    assert snapshot["step_retries_total"] == 3
    assert snapshot["step_retries_by_name"]["Supervisor"] == 2


def test_record_dreaming_jobs() -> None:
    registry = MetricsRegistry()
    registry.record_dreaming_job(success=True)
    registry.record_dreaming_job(success=False)

    snapshot = registry.snapshot()
    assert snapshot["dreaming_jobs"]["completed"] == 1
    assert snapshot["dreaming_jobs"]["failed"] == 1


def test_record_token_usage() -> None:
    registry = MetricsRegistry()
    registry.record_token_usage(input_tokens=100, output_tokens=40, requests=1)
    registry.record_token_usage(input_tokens=50, output_tokens=10, requests=1)

    snapshot = registry.snapshot()
    assert snapshot["tokens"]["input_total"] == 150
    assert snapshot["tokens"]["output_total"] == 50
    assert snapshot["tokens"]["total"] == 200
    assert snapshot["tokens"]["requests_total"] == 2
