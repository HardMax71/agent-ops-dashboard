import functools
import json
import logging
from collections.abc import Callable, Coroutine

import redis.asyncio as aioredis

_logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"killed", "done", "failed", "timed_out"})


def worker_error_handler(
    fn: Callable[..., Coroutine[object, object, None]],
) -> Callable[..., Coroutine[object, object, None]]:
    """Publish job.failed to the Redis SSE channel on unhandled exceptions.

    Applied to all ARQ worker functions. Re-raises so ARQ records the job as FAILED.
    """

    fn_name = fn.__name__  # type: ignore[attr-defined]

    @functools.wraps(fn)
    async def wrapper(ctx: dict[str, object], job_id: str, *args: object, **kwargs: object) -> None:
        try:
            await fn(ctx, job_id, *args, **kwargs)
        except Exception as exc:
            redis: aioredis.Redis = ctx["redis"]  # type: ignore[assignment]
            _logger.exception("Worker function %s failed for job %s", fn_name, job_id)
            raw = await redis.get(f"job:{job_id}")
            if raw is not None:
                data = json.loads(raw)
                if data.get("status") not in _TERMINAL_STATUSES:
                    await redis.publish(
                        f"jobs:{job_id}:events",
                        json.dumps({"type": "job.failed", "error": str(exc)}),
                    )
                    data["status"] = "failed"
                    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))
                    owner_id: str = data.get("owner_id", "anonymous")
                    await redis.decr(f"active_jobs:{owner_id}")
            raise

    return wrapper
