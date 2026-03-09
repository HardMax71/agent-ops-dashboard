"""Service-wide ARQ worker error handler (PRD-003-1 §10)."""

import functools
import json
import logging
from collections.abc import Callable, Coroutine

import redis.asyncio as aioredis

_logger = logging.getLogger(__name__)


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
            await redis.publish(
                f"jobs:{job_id}:events",
                json.dumps({"type": "job.failed", "error": str(exc)}),
            )
            raise

    return wrapper
