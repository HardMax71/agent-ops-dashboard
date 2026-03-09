import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis import FakeAsyncRedis

from agentops.worker import TIMEOUT_ANSWER, expire_human_input, job_timeout_cleaner


@pytest.fixture
def mock_graph():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=None)
    graph.aget_state = AsyncMock()
    return graph


@pytest.fixture
def fake_redis_worker():
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def ctx(fake_redis_worker, mock_graph):
    return {"redis": fake_redis_worker, "graph": mock_graph}


async def test_expire_provides_timeout_answer(ctx, fake_redis_worker, mock_graph):
    """expire_human_input resumes with TIMEOUT_ANSWER when job is still waiting."""
    job_data = {"job_id": "j1", "status": "waiting", "awaiting_human": True}
    await fake_redis_worker.setex("job:j1", 86400, json.dumps(job_data))

    # Simulate an active interrupt
    mock_graph.aget_state.return_value = MagicMock(tasks=["pending_task"])

    await expire_human_input(ctx, "j1")

    # Verify graph was resumed with timeout answer
    mock_graph.ainvoke.assert_called_once()
    call_args = mock_graph.ainvoke.call_args
    command = call_args[0][0]
    assert command.resume == TIMEOUT_ANSWER

    # Verify Redis updated
    raw = await fake_redis_worker.get("job:j1")
    data = json.loads(raw)
    assert data["status"] == "running"
    assert data["awaiting_human"] is False


async def test_expire_skips_completed_jobs(ctx, fake_redis_worker, mock_graph):
    """expire_human_input does nothing when job is already done."""
    job_data = {"job_id": "j2", "status": "done", "awaiting_human": False}
    await fake_redis_worker.setex("job:j2", 86400, json.dumps(job_data))

    await expire_human_input(ctx, "j2")

    mock_graph.ainvoke.assert_not_called()
    mock_graph.aget_state.assert_not_called()


async def test_expire_skips_missing_jobs(ctx, mock_graph):
    """expire_human_input does nothing when job doesn't exist."""
    await expire_human_input(ctx, "nonexistent")
    mock_graph.ainvoke.assert_not_called()


async def test_timeout_cleaner_transitions_stale_jobs(ctx, fake_redis_worker):
    """job_timeout_cleaner transitions waiting jobs older than threshold to timed_out."""
    stale_time = str(int(time.time()) - 700)  # 700s ago (> 600s threshold)
    job_data = {
        "job_id": "j3",
        "status": "waiting",
        "awaiting_human": True,
        "waiting_since": stale_time,
    }
    await fake_redis_worker.setex("job:j3", 86400, json.dumps(job_data))

    await job_timeout_cleaner(ctx)

    raw = await fake_redis_worker.get("job:j3")
    data = json.loads(raw)
    assert data["status"] == "timed_out"


async def test_timeout_cleaner_leaves_fresh_jobs(ctx, fake_redis_worker):
    """job_timeout_cleaner doesn't touch recently-waiting jobs."""
    fresh_time = str(int(time.time()) - 60)  # 60s ago (< 600s threshold)
    job_data = {
        "job_id": "j4",
        "status": "waiting",
        "awaiting_human": True,
        "waiting_since": fresh_time,
    }
    await fake_redis_worker.setex("job:j4", 86400, json.dumps(job_data))

    await job_timeout_cleaner(ctx)

    raw = await fake_redis_worker.get("job:j4")
    data = json.loads(raw)
    assert data["status"] == "waiting"


async def test_timeout_cleaner_skips_non_waiting(ctx, fake_redis_worker):
    """job_timeout_cleaner ignores jobs that aren't in 'waiting' status."""
    job_data = {"job_id": "j5", "status": "running"}
    await fake_redis_worker.setex("job:j5", 86400, json.dumps(job_data))

    await job_timeout_cleaner(ctx)

    raw = await fake_redis_worker.get("job:j5")
    data = json.loads(raw)
    assert data["status"] == "running"
