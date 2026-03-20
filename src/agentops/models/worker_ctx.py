from typing import TypedDict

import redis.asyncio as aioredis
from arq import ArqRedis
from langgraph.graph.state import CompiledStateGraph


class WorkerContext(TypedDict, total=False):
    redis: aioredis.Redis
    arq: ArqRedis
    graph: CompiledStateGraph
    metrics_httpd: object
    meter_provider: object
    _graph_cm: object
