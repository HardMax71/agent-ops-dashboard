import json

from agentops.config import get_settings
from agentops.metrics.setup import configure_worker_metrics
from agentops.tasks.codebase import build_codebase_index, update_codebase_index
from agentops.tasks.triage import expire_human_input


async def on_startup(ctx: dict) -> None:  # noqa: ANN001
    import redis.asyncio as aioredis

    settings = get_settings()
    ctx["redis"] = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    configure_worker_metrics(port=8002)


async def on_shutdown(ctx: dict) -> None:  # noqa: ANN001
    await ctx["redis"].aclose()


async def run_triage(ctx: dict, job_id: str) -> None:  # noqa: ANN001
    """Run the triage graph for a job."""
    redis = ctx["redis"]
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        return

    data = json.loads(raw)
    data["status"] = "running"
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))


class WorkerSettings:
    functions = [run_triage, expire_human_input, build_codebase_index, update_codebase_index]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
