from typing import TypedDict

import redis.asyncio as aioredis
from arq import ArqRedis
from fastapi import Request, Response

from agentops.config import Settings
from agentops.graphql.types import UserInfo


class GraphQLContext(TypedDict):
    request: Request
    response: Response
    user: UserInfo | None
    redis: aioredis.Redis
    arq: ArqRedis
    settings: Settings
