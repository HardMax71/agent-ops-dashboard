import json
import logging
import time

import redis.asyncio as aioredis
from arq.cron import cron
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agentops.config import get_settings
from agentops.events.interrupt import check_for_interrupt
from agentops.events.transformer import LangGraphEventTransformer
from agentops.graph.graph import create_graph_with_postgres
from agentops.graph.state import BugTriageState
from agentops.metrics.setup import configure_metrics, shutdown_metrics
from agentops.worker_middleware import worker_error_handler

_logger = logging.getLogger(__name__)

TIMEOUT_ANSWER = "No human response received within the allowed time window."
_HUMAN_TIMEOUT_SECONDS = 1800  # 30 minutes
_JOB_STALE_SECONDS = 600  # 10 minutes for cron cleaner
_TERMINAL_STATES = frozenset({"killed", "done", "failed", "timed_out"})

_transformer = LangGraphEventTransformer()


async def on_startup(ctx: dict) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    settings = get_settings()
    ctx["redis"] = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    if settings.environment != "test":
        httpd, provider = configure_metrics(port=settings.worker_metrics_port)
        ctx["metrics_httpd"] = httpd
        ctx["meter_provider"] = provider
    else:
        ctx["metrics_httpd"] = None
        ctx["meter_provider"] = None

    # Build graph (PostgreSQL checkpointer)
    ctx["graph"] = await create_graph_with_postgres(settings.psycopg_dsn)


async def on_shutdown(ctx: dict) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    await ctx["redis"].aclose()
    httpd = ctx.get("metrics_httpd")
    if httpd is not None:
        shutdown_metrics(httpd)


@worker_error_handler
async def run_triage(ctx: dict, job_id: str) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    """Execute the bug triage graph for a job with SSE streaming."""
    redis_client: aioredis.Redis = ctx["redis"]
    graph = ctx["graph"]

    raw = await redis_client.get(f"job:{job_id}")
    if raw is None:
        _logger.warning("run_triage: job not found in Redis for job_id=%s", job_id)
        return

    data = json.loads(raw)

    # Guard: skip if job already reached a terminal state
    if data.get("status") in _TERMINAL_STATES:
        return

    data["status"] = "running"
    await redis_client.setex(f"job:{job_id}", 86400, json.dumps(data))

    initial_state = BugTriageState(
        job_id=job_id,
        issue_url=data["issue_url"],
        status="running",
        supervisor_notes=data.get("supervisor_notes", ""),
    )

    config: RunnableConfig = {"configurable": {"thread_id": job_id}}
    channel = f"jobs:{job_id}:events"

    # Stream events via astream_events and publish to Redis Pub/Sub
    spawned_agents: dict[str, str] = {}

    async for event in graph.astream_events(
        initial_state.model_dump(), config=config, version="v2"
    ):
        for sse in _transformer.transform(event, spawned_agents):
            await redis_client.publish(channel, json.dumps(sse))

    # Re-read fresh data to detect concurrent status changes (pause/kill)
    fresh_raw = await redis_client.get(f"job:{job_id}")
    if fresh_raw is None:
        return
    data = json.loads(fresh_raw)

    if data.get("status") in _TERMINAL_STATES:
        return

    if data.get("paused") or data.get("status") == "pausing":
        data["status"] = "paused"
        await redis_client.setex(f"job:{job_id}", 86400, json.dumps(data))
        return

    # Check for interrupt (human input requested)
    interrupt_payload = await check_for_interrupt(graph, config)

    if interrupt_payload is not None:
        # Job is interrupted — waiting for human input
        await redis_client.publish(
            channel,
            json.dumps(
                {
                    "type": "graph.interrupt",
                    "question": interrupt_payload.question,
                    "context": interrupt_payload.context,
                }
            ),
        )

        data["status"] = "waiting"
        data["awaiting_human"] = True
        data["waiting_since"] = str(int(time.time()))
        await redis_client.setex(f"job:{job_id}", 86400, json.dumps(data))

        # Schedule timeout for human input
        arq_pool = ctx.get("arq")
        if arq_pool:
            await arq_pool.enqueue_job(
                "expire_human_input", job_id, _defer_by=_HUMAN_TIMEOUT_SECONDS
            )
    else:
        # Job completed
        await redis_client.publish(channel, json.dumps({"type": "job.done"}))
        data["status"] = "done"
        await redis_client.setex(f"job:{job_id}", 86400, json.dumps(data))


async def expire_human_input(ctx: dict, job_id: str) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    """Resume a timed-out human input with a default answer."""
    redis_client = ctx["redis"]
    graph = ctx["graph"]

    raw = await redis_client.get(f"job:{job_id}")
    if raw is None:
        return

    data = json.loads(raw)
    if data.get("status") != "waiting":
        return

    config = {"configurable": {"thread_id": job_id}}
    state_snapshot = await graph.aget_state(config)
    if not state_snapshot.tasks:
        return

    # Resume with timeout answer
    await graph.ainvoke(Command(resume=TIMEOUT_ANSWER), config=config)

    # Re-read fresh data to detect concurrent status changes (kill)
    fresh_raw = await redis_client.get(f"job:{job_id}")
    if fresh_raw is None:
        return
    data = json.loads(fresh_raw)

    if data.get("status") in _TERMINAL_STATES:
        return

    data["status"] = "running"
    data["awaiting_human"] = False
    await redis_client.setex(f"job:{job_id}", 86400, json.dumps(data))


async def job_timeout_cleaner(ctx: dict) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    """Cron job: transition stale waiting jobs to timed_out."""
    redis_client = ctx["redis"]
    now = int(time.time())
    cursor = b"0"

    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match="job:*", count=100)
        for key in keys:
            raw = await redis_client.get(key)
            if raw is None:
                continue
            data = json.loads(raw)
            if data.get("status") != "waiting":
                continue
            waiting_since = int(data.get("waiting_since", "0"))
            if waiting_since > 0 and (now - waiting_since) > _JOB_STALE_SECONDS:
                data["status"] = "timed_out"
                await redis_client.setex(key, 86400, json.dumps(data))
                _logger.info("job_timeout_cleaner: %s → timed_out", key)

        if cursor == 0:
            break


class WorkerSettings:
    functions = [run_triage, expire_human_input]
    cron_jobs = [cron(job_timeout_cleaner, minute={0, 15, 30, 45}, unique=True)]  # type: ignore[arg-type]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
    allow_abort_jobs = True
