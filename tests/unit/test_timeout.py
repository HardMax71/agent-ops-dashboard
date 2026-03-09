import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentops.worker import TIMEOUT_ANSWER, expire_human_input, job_timeout_cleaner, run_triage


@pytest.fixture
def mock_graph():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=None)
    graph.aget_state = AsyncMock()

    # Default: astream_events returns an empty async generator
    async def _empty_stream(*_args, **_kwargs):
        return
        yield  # noqa: RET504

    graph.astream_events = _empty_stream
    return graph


@pytest.fixture
def ctx(fake_redis, mock_graph):
    return {"redis": fake_redis, "graph": mock_graph}


async def test_expire_provides_timeout_answer(ctx, fake_redis, mock_graph, make_job):
    """expire_human_input resumes with TIMEOUT_ANSWER when job is still waiting."""
    await make_job("j1", status="waiting", awaiting_human=True)

    # Simulate an active interrupt
    mock_graph.aget_state.return_value = MagicMock(tasks=["pending_task"])

    await expire_human_input(ctx, "j1")

    # Verify graph was resumed with timeout answer
    mock_graph.ainvoke.assert_called_once()
    call_args = mock_graph.ainvoke.call_args
    command = call_args[0][0]
    assert command.resume == TIMEOUT_ANSWER

    # Verify Redis updated
    raw = await fake_redis.get("job:j1")
    data = json.loads(raw)
    assert data["status"] == "running"
    assert data["awaiting_human"] is False


async def test_expire_skips_completed_jobs(ctx, mock_graph, make_job):
    """expire_human_input does nothing when job is already done."""
    await make_job("j2", status="done", awaiting_human=False)

    await expire_human_input(ctx, "j2")

    mock_graph.ainvoke.assert_not_called()
    mock_graph.aget_state.assert_not_called()


async def test_expire_skips_missing_jobs(ctx, mock_graph):
    """expire_human_input does nothing when job doesn't exist."""
    await expire_human_input(ctx, "nonexistent")
    mock_graph.ainvoke.assert_not_called()


async def test_timeout_cleaner_transitions_stale_jobs(ctx, fake_redis, make_job):
    """job_timeout_cleaner transitions waiting jobs older than threshold to timed_out."""
    stale_time = str(int(time.time()) - 700)  # 700s ago (> 600s threshold)
    await make_job("j3", status="waiting", awaiting_human=True, waiting_since=stale_time)

    await job_timeout_cleaner(ctx)

    raw = await fake_redis.get("job:j3")
    data = json.loads(raw)
    assert data["status"] == "timed_out"


async def test_timeout_cleaner_leaves_fresh_jobs(ctx, fake_redis, make_job):
    """job_timeout_cleaner doesn't touch recently-waiting jobs."""
    fresh_time = str(int(time.time()) - 60)  # 60s ago (< 600s threshold)
    await make_job("j4", status="waiting", awaiting_human=True, waiting_since=fresh_time)

    await job_timeout_cleaner(ctx)

    raw = await fake_redis.get("job:j4")
    data = json.loads(raw)
    assert data["status"] == "waiting"


async def test_timeout_cleaner_skips_non_waiting(ctx, fake_redis, make_job):
    """job_timeout_cleaner ignores jobs that aren't in 'waiting' status."""
    await make_job("j5", status="running")

    await job_timeout_cleaner(ctx)

    raw = await fake_redis.get("job:j5")
    data = json.loads(raw)
    assert data["status"] == "running"


async def test_run_triage_skips_killed_job(ctx, fake_redis, mock_graph, make_job):
    """run_triage returns early without invoking the graph when job is already killed."""
    await make_job("j6", status="killed")

    await run_triage(ctx, "j6")

    raw = await fake_redis.get("job:j6")
    data = json.loads(raw)
    assert data["status"] == "killed"


async def test_run_triage_respects_kill_during_execution(ctx, fake_redis, mock_graph, make_job):
    """run_triage preserves killed status when kill happens during graph execution."""
    await make_job("j7", status="queued")
    mock_graph.aget_state.return_value = MagicMock(tasks=[])

    async def simulate_kill(*_args, **_kwargs):
        # Simulate API killing the job while astream_events is running
        raw = await fake_redis.get("job:j7")
        data = json.loads(raw)
        data["status"] = "killed"
        await fake_redis.setex("job:j7", 86400, json.dumps(data))
        return
        yield  # noqa: RET504

    mock_graph.astream_events = simulate_kill

    await run_triage(ctx, "j7")

    raw = await fake_redis.get("job:j7")
    data = json.loads(raw)
    assert data["status"] == "killed"


async def test_run_triage_respects_pause_during_execution(ctx, fake_redis, mock_graph, make_job):
    """run_triage sets status to paused when pause happens during graph execution."""
    await make_job("j8", status="queued")
    mock_graph.aget_state.return_value = MagicMock(tasks=[])

    async def simulate_pause(*_args, **_kwargs):
        # Simulate API pausing the job while astream_events is running
        raw = await fake_redis.get("job:j8")
        data = json.loads(raw)
        data["status"] = "pausing"
        data["paused"] = True
        await fake_redis.setex("job:j8", 86400, json.dumps(data))
        return
        yield  # noqa: RET504

    mock_graph.astream_events = simulate_pause

    await run_triage(ctx, "j8")

    raw = await fake_redis.get("job:j8")
    data = json.loads(raw)
    assert data["status"] == "paused"


async def test_expire_skips_killed_during_resume(ctx, fake_redis, mock_graph, make_job):
    """expire_human_input preserves killed status when kill happens during graph resume."""
    await make_job("j9", status="waiting", awaiting_human=True)
    mock_graph.aget_state.return_value = MagicMock(tasks=["pending_task"])

    async def simulate_kill(*_args, **_kwargs):
        raw = await fake_redis.get("job:j9")
        data = json.loads(raw)
        data["status"] = "killed"
        await fake_redis.setex("job:j9", 86400, json.dumps(data))
        return None

    mock_graph.ainvoke = AsyncMock(side_effect=simulate_kill)

    await expire_human_input(ctx, "j9")

    raw = await fake_redis.get("job:j9")
    data = json.loads(raw)
    assert data["status"] == "killed"
