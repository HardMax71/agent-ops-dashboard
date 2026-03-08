from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Request


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]
