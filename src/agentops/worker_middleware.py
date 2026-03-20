import functools
import json
import logging
from collections.abc import Callable, Coroutine

import redis.asyncio as aioredis

from agentops.models.job import TERMINAL_STATUSES, JobData
from agentops.models.worker_ctx import WorkerContext

_logger = logging.getLogger(__name__)


def worker_error_handler(
    fn: Callable[..., Coroutine[object, object, None]],
) -> Callable[..., Coroutine[object, object, None]]:
    """Publish job.failed to the Redis SSE channel on unhandled exceptions.

    Applied to all ARQ worker functions. Re-raises so ARQ records the job as FAILED.
    """

    fn_name = fn.__name__  # type: ignore[attr-defined]

    @functools.wraps(fn)
    async def wrapper(ctx: WorkerContext, job_id: str, *args: object, **kwargs: object) -> None:
        try:
            await fn(ctx, job_id, *args, **kwargs)
        except Exception as exc:
            redis: aioredis.Redis = ctx["redis"]
            _logger.exception("Worker function %s failed for job %s", fn_name, job_id)
            raw = await redis.get(f"job:{job_id}")
            if raw is not None:
                data = JobData.model_validate_json(raw)
                if data.status not in TERMINAL_STATUSES:
                    await redis.publish(
                        f"jobs:{job_id}:events",
                        json.dumps({"type": "job.failed", "error": str(exc)}),
                    )
                    data.status = "failed"
                    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
                    await redis.decr(f"active_jobs:{data.owner_id or 'anonymous'}")
            raise

    return wrapper
