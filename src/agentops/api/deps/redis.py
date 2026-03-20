from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from starlette.requests import HTTPConnection


async def get_redis(connection: HTTPConnection) -> aioredis.Redis:
    return connection.app.state.redis


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]
