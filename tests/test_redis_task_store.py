"""RedisTaskStore 单元测试。"""

import pytest

fakeredis = pytest.importorskip("fakeredis")

from herness.api.store import RedisTaskStore
from herness.models.task import TaskRequest, TaskResult, TaskStatus


def test_redis_task_store_lifecycle() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    store = RedisTaskStore("redis://unused", ttl_seconds=3600, redis_client=fake)

    record = store.create(TaskRequest(user_id="u1", input="hello"))
    task_id = record.task_id

    fetched = store.get(task_id)
    assert fetched is not None
    assert fetched.status == TaskStatus.PENDING

    store.mark_running(task_id)
    running = store.get(task_id)
    assert running is not None
    assert running.status == TaskStatus.RUNNING

    store.complete(
        TaskResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            answer="done",
            rounds_used=1,
        )
    )
    done = store.get(task_id)
    assert done is not None
    assert done.status == TaskStatus.COMPLETED
    assert done.result is not None
    assert done.result.answer == "done"

    store.close()
