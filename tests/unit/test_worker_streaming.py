"""Tests for worker run_triage with SSE streaming."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis import FakeAsyncRedis

from agentops.worker import run_triage

pytestmark = pytest.mark.asyncio


@pytest.fixture
def worker_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def mock_graph() -> MagicMock:
    graph = MagicMock()

    # astream_events returns an async iterator
    async def _empty_stream(*_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
        return
        yield  # make it an async generator  # noqa: RET504

    graph.astream_events = _empty_stream

    # aget_state returns a snapshot with no tasks (graph completed)
    state_snapshot = MagicMock()
    state_snapshot.tasks = []
    graph.aget_state = AsyncMock(return_value=state_snapshot)

    return graph


class TestRunTriageStreaming:
    async def test_publishes_done_event(
        self, worker_redis: FakeAsyncRedis, mock_graph: MagicMock
    ) -> None:
        job_data = {
            "job_id": "j1",
            "status": "queued",
            "issue_url": "https://github.com/a/b/issues/1",
            "supervisor_notes": "",
        }
        await worker_redis.setex("job:j1", 86400, json.dumps(job_data))

        # Track published messages
        published: list[str] = []
        original_publish = worker_redis.publish

        async def _track_publish(channel: str, message: str) -> int:
            published.append(message)
            return await original_publish(channel, message)

        worker_redis.publish = _track_publish  # type: ignore[assignment]

        ctx: dict[str, object] = {"redis": worker_redis, "graph": mock_graph}
        await run_triage(ctx, "j1")

        # Should have published job.done
        done_events = [p for p in published if "job.done" in p]
        assert len(done_events) == 1

        # Job status should be "done"
        raw = await worker_redis.get("job:j1")
        assert raw is not None
        assert json.loads(raw)["status"] == "done"

    async def test_skips_terminal_state(
        self, worker_redis: FakeAsyncRedis, mock_graph: MagicMock
    ) -> None:
        job_data = {
            "job_id": "j2",
            "status": "killed",
            "issue_url": "https://github.com/a/b/issues/1",
        }
        await worker_redis.setex("job:j2", 86400, json.dumps(job_data))

        ctx: dict[str, object] = {"redis": worker_redis, "graph": mock_graph}
        await run_triage(ctx, "j2")

        raw = await worker_redis.get("job:j2")
        assert raw is not None
        assert json.loads(raw)["status"] == "killed"

    async def test_publishes_interrupt_event(
        self, worker_redis: FakeAsyncRedis, mock_graph: MagicMock
    ) -> None:
        job_data = {
            "job_id": "j3",
            "status": "queued",
            "issue_url": "https://github.com/a/b/issues/1",
            "supervisor_notes": "",
        }
        await worker_redis.setex("job:j3", 86400, json.dumps(job_data))

        # Mock an interrupt
        interrupt_val = MagicMock()
        interrupt_val.question = "What should I do?"
        interrupt_val.context = "Some context"

        interrupt_obj = MagicMock()
        interrupt_obj.value = interrupt_val

        task = MagicMock()
        task.interrupts = [interrupt_obj]

        state_snapshot = MagicMock()
        state_snapshot.tasks = [task]
        mock_graph.aget_state = AsyncMock(return_value=state_snapshot)

        published: list[str] = []
        original_publish = worker_redis.publish

        async def _track_publish(channel: str, message: str) -> int:
            published.append(message)
            return await original_publish(channel, message)

        worker_redis.publish = _track_publish  # type: ignore[assignment]

        ctx: dict[str, object] = {"redis": worker_redis, "graph": mock_graph}
        await run_triage(ctx, "j3")

        interrupt_events = [p for p in published if "graph.interrupt" in p]
        assert len(interrupt_events) == 1

        raw = await worker_redis.get("job:j3")
        assert raw is not None
        data = json.loads(raw)
        assert data["status"] == "waiting"
        assert data["awaiting_human"] is True
