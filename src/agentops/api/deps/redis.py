from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Request


async def get_redis(request: Request) -> aioredis.Redis:  # type: ignore[type-arg]
    return request.app.state.redis  # type: ignore[no-any-return]


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]  # type: ignore[type-arg]
