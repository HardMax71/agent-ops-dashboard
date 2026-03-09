import json
import logging

import redis.asyncio as aioredis

from agentops.config import get_settings
from agentops.metrics.setup import configure_metrics, shutdown_metrics

_logger = logging.getLogger(__name__)


async def on_startup(ctx: dict) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    settings = get_settings()
    ctx["redis"] = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    httpd, provider = configure_metrics(port=8002)
    ctx["metrics_httpd"] = httpd
    ctx["meter_provider"] = provider


async def on_shutdown(ctx: dict) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    await ctx["redis"].aclose()
    shutdown_metrics(ctx["metrics_httpd"])


async def run_triage(ctx: dict, job_id: str) -> None:  # noqa: ANN401 — ARQ ctx is untyped dict
    """Stub triage task — full implementation in Phase 3."""
    redis = ctx["redis"]
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        _logger.warning("run_triage: job not found in Redis for job_id=%s", job_id)
        return
    data = json.loads(raw)
    data["status"] = "running"
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))


class WorkerSettings:
    functions = [run_triage]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
