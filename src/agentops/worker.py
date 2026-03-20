import json
import logging
import time

import redis.asyncio as aioredis
from arq.cron import cron
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agentops.config import Environment, get_settings
from agentops.events.interrupt import check_for_interrupt
from agentops.events.transformer import LangGraphEventTransformer
from agentops.graph.graph import create_graph_with_postgres
from agentops.graph.state import BugTriageState
from agentops.metrics.setup import configure_metrics, shutdown_metrics
from agentops.tasks.codebase import build_codebase_index, update_codebase_index
from agentops.worker_middleware import worker_error_handler

_logger = logging.getLogger(__name__)

TIMEOUT_ANSWER = "No human response received within the allowed time window."
_HUMAN_TIMEOUT_SECONDS = 1800  # 30 minutes
_JOB_STALE_SECONDS = 1800  # 30 minutes for cron cleaner
_TERMINAL_STATES = frozenset({"killed", "done", "failed", "timed_out"})


async def _decrement_active_jobs(
    redis_client: aioredis.Redis,
    owner_id: str,
) -> None:
    await redis_client.decr(f"active_jobs:{owner_id}")


async def on_startup(ctx: dict) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    settings = get_settings()
    ctx["arq"] = ctx["redis"]
    ctx["redis"] = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    if settings.environment != Environment.TEST:
        httpd, provider = configure_metrics(port=settings.worker_metrics_port)
        ctx["metrics_httpd"] = httpd
        ctx["meter_provider"] = provider
    else:
        ctx["metrics_httpd"] = None
        ctx["meter_provider"] = None

    graph_cm = create_graph_with_postgres(settings.psycopg_dsn)
    ctx["_graph_cm"] = graph_cm
    ctx["graph"] = await graph_cm.__aenter__()


async def on_shutdown(ctx: dict) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    graph_cm = ctx.get("_graph_cm")
    if graph_cm is not None:
        await graph_cm.__aexit__(None, None, None)
    await ctx["redis"].aclose()
    httpd = ctx.get("metrics_httpd")
    if httpd is not None:
        shutdown_metrics(httpd)


async def _stream_and_finalize(
    ctx: dict,  # noqa: ANN401
    job_id: str,
    graph_input: object,  # noqa: ANN401
) -> None:
    redis_client: aioredis.Redis = ctx["redis"]
    graph = ctx["graph"]
    arq_pool = ctx.get("arq")

    config: RunnableConfig = {"configurable": {"thread_id": job_id}}
    channel = f"jobs:{job_id}:events"
    transformer = LangGraphEventTransformer()

    async for event in graph.astream_events(graph_input, config=config, version="v2"):
        for sse in transformer.transform(event):
            await redis_client.publish(channel, json.dumps(sse))

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

    interrupt_payload = await check_for_interrupt(graph, config)

    if interrupt_payload is not None:
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

        if arq_pool:
            await arq_pool.enqueue_job(
                "expire_human_input",
                job_id,
                _job_id=f"timeout:{job_id}",
                _defer_by=_HUMAN_TIMEOUT_SECONDS,
            )
    else:
        # Persist triage report fields from final graph state
        config_for_state: RunnableConfig = {"configurable": {"thread_id": job_id}}
        final_state = await graph.aget_state(config_for_state)
        vals: dict[str, object] = getattr(final_state, "values", None) or {}
        report: dict[str, object] = vals.get("report") or {}
        if report and "severity" in report:
            data["github_comment"] = report.get("github_comment", "")
            data["severity"] = report.get("severity", "")
            data["relevant_files"] = report.get("relevant_files", [])
            data["recommended_fix"] = report.get("recommended_fix", "")
            data["ticket_title"] = report.get("ticket_title", "")
            data["ticket_labels"] = report.get("ticket_labels", [])

        await redis_client.publish(channel, json.dumps({"type": "job.done"}))
        data["status"] = "done"
        await redis_client.setex(f"job:{job_id}", 86400, json.dumps(data))
        await _decrement_active_jobs(redis_client, data.get("owner_id", "anonymous"))


@worker_error_handler
async def run_triage(ctx: dict, job_id: str) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    redis_client: aioredis.Redis = ctx["redis"]

    raw = await redis_client.get(f"job:{job_id}")
    if raw is None:
        _logger.warning("run_triage: job not found for job_id=%s", job_id)
        return

    data = json.loads(raw)
    if data.get("status") in _TERMINAL_STATES:
        return

    data["status"] = "running"
    await redis_client.setex(f"job:{job_id}", 86400, json.dumps(data))

    initial_state = BugTriageState(
        job_id=job_id,
        issue_url=data["issue_url"],
        issue_title=data.get("issue_title", ""),
        issue_body=data.get("issue_body", ""),
        repository=data.get("repository", ""),
        owner_id=data.get("owner_id", ""),
        status="running",
        supervisor_notes=data.get("supervisor_notes", ""),
    )
    await _stream_and_finalize(ctx, job_id, initial_state.model_dump())


@worker_error_handler
async def resume_graph(  # noqa: ANN401 — ARQ ctx is untyped dict
    ctx: dict,
    job_id: str,
    resume_value: str,
    parse_as_json: bool = False,
) -> None:
    """Resume a graph from an interrupt (human answer, unpause, redirect)."""
    redis_client: aioredis.Redis = ctx["redis"]

    raw = await redis_client.get(f"job:{job_id}")
    if raw is None:
        return

    data = json.loads(raw)
    if data.get("status") in _TERMINAL_STATES:
        return

    parsed_value: str | dict[str, str] = json.loads(resume_value) if parse_as_json else resume_value

    await _stream_and_finalize(ctx, job_id, Command(resume=parsed_value))


async def expire_human_input(ctx: dict, job_id: str) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
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

    await _stream_and_finalize(ctx, job_id, Command(resume=TIMEOUT_ANSWER))


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
                data["awaiting_human"] = False
                await redis_client.setex(key, 86400, json.dumps(data))
                await _decrement_active_jobs(
                    redis_client,
                    data.get("owner_id", "anonymous"),
                )
                _logger.info("job_timeout_cleaner: %s → timed_out", key)

        if cursor == 0:
            break


class WorkerSettings:
    functions = [
        run_triage,
        expire_human_input,
        resume_graph,
        build_codebase_index,
        update_codebase_index,
    ]
    cron_jobs = [cron(job_timeout_cleaner, minute={0, 15, 30, 45}, unique=True)]  # type: ignore[arg-type]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
    allow_abort_jobs = True
