from agentops.models.job import JobData
from agentops.models.worker_ctx import WorkerContext

TIMEOUT_ANSWER = "[no answer provided — proceeding with best-effort]"


async def expire_human_input(ctx: WorkerContext, job_id: str) -> None:
    """Handle expired human input by providing default answer."""
    from redis.asyncio import Redis

    redis: Redis = ctx["redis"]
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        return
    data = JobData.model_validate_json(raw)
    data.status = "running"
    data.awaiting_human = False
    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
    await redis.setex(f"job:{job_id}:answer", 3600, TIMEOUT_ANSWER)
