from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from http.server import HTTPServer

import redis.asyncio as aioredis
from arq import ArqRedis
from arq import create_pool as create_arq_pool
from arq.connections import RedisSettings as ArqRedisSettings
from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentops.config import get_settings
from agentops.graph.graph import create_graph_with_postgres
from agentops.metrics.setup import configure_metrics, shutdown_metrics


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # Database engine is created first — always disposed in finally.
    engine = create_async_engine(settings.database_url)
    app.state.db_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    redis_client: aioredis.Redis | None = None
    arq_pool: ArqRedis | None = None
    httpd: HTTPServer | None = None
    graph_cm: AsyncGenerator[CompiledStateGraph, None] | None = None

    try:
        # Redis pool
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        app.state.redis = redis_client

        # ArqRedis pool for job control from API endpoints
        arq_pool = await create_arq_pool(ArqRedisSettings.from_dsn(settings.redis_url))
        app.state.arq = arq_pool

        # OTel metrics (API process)
        httpd, provider = configure_metrics(port=settings.api_metrics_port)
        app.state.metrics_httpd = httpd
        app.state.meter_provider = provider

        # Graph (PostgreSQL checkpointer kept alive for the app lifespan)
        graph_cm = create_graph_with_postgres(settings.psycopg_dsn)
        graph = await graph_cm.__aenter__()
        app.state.graph = graph

        yield
    finally:
        if graph_cm is not None:
            await graph_cm.__aexit__(None, None, None)
        if arq_pool is not None:
            await arq_pool.aclose()
        if redis_client is not None:
            await redis_client.aclose()
        await engine.dispose()
        if httpd is not None:
            shutdown_metrics(httpd)
