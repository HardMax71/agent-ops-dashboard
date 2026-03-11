import json

TIMEOUT_ANSWER = "[no answer provided — proceeding with best-effort]"


async def expire_human_input(ctx: dict[str, object], job_id: str) -> None:
    """Handle expired human input by providing default answer."""
    from redis.asyncio import Redis

    redis: Redis = ctx["redis"]  # type: ignore[assignment]
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        return
    data = json.loads(raw)
    data["status"] = "running"
    data["awaiting_human"] = False
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))
    await redis.setex(f"job:{job_id}:answer", 3600, TIMEOUT_ANSWER)
