from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from arq import create_pool as create_arq_pool
from arq.connections import RedisSettings as ArqRedisSettings
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentops.config import get_settings
from agentops.graph.graph import create_graph_with_postgres
from agentops.metrics.setup import configure_metrics, shutdown_metrics


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # Database session factory
    engine = create_async_engine(settings.database_url)
    app.state.db_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Redis pool
    app.state.redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    # Graph (PostgreSQL checkpointer)
    app.state.graph = await create_graph_with_postgres(settings.psycopg_dsn)

    # ArqRedis pool for job control from API endpoints
    app.state.arq = await create_arq_pool(ArqRedisSettings.from_dsn(settings.redis_url))

    # OTel metrics (API process)
    httpd, provider = configure_metrics(port=settings.api_metrics_port)
    app.state.metrics_httpd = httpd
    app.state.meter_provider = provider

    yield

    await app.state.arq.aclose()
    await app.state.redis.aclose()
    await engine.dispose()
    shutdown_metrics(app.state.metrics_httpd)
