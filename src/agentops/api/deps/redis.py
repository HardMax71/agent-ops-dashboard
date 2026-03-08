from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status


async def get_redis(request: Request) -> aioredis.Redis:  # type: ignore[type-arg]
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available",
        )
    return redis  # type: ignore[return-value]


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]  # type: ignore[type-arg]
