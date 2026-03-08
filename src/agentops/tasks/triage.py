
TIMEOUT_ANSWER = "[no answer provided — proceeding with best-effort]"


async def expire_human_input(ctx: dict, job_id: str) -> None:
    """Handle expired human input by providing default answer."""
    redis = ctx["redis"]
    await redis.hset(f"job:{job_id}", mapping={"status": "running", "awaiting_human": "false"})
    await redis.setex(f"job:{job_id}:answer", 3600, TIMEOUT_ANSWER)
