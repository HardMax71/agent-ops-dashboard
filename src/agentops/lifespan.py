from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentops.config import get_settings
from agentops.metrics.setup import configure_api_metrics, shutdown_api_metrics


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

    # OTel metrics (API process)
    configure_api_metrics(port=8001)

    yield

    await app.state.redis.aclose()
    await engine.dispose()
    shutdown_api_metrics()
