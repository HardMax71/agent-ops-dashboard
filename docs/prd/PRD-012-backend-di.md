---
id: PRD-012
title: Backend Architecture & Dependency Injection Standards
status: DRAFT
domain: backend
depends_on: [ PRD-003, PRD-006, PRD-007, PRD-008, PRD-011 ]
key_decisions: [ no-nullable-deps, no-conditional-fallback, srp-dep-modules, lifespan-singletons, arq-ctx-only, dependency-overrides-testing ]
---

# PRD-012 — Backend Architecture & Dependency Injection Standards

| Field        | Value                                                                                                                                                                                                            |
|--------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Document ID  | PRD-012                                                                                                                                                                                                          |
| Version      | 1.0                                                                                                                                                                                                              |
| Status       | DRAFT                                                                                                                                                                                                            |
| Date         | March 2026                                                                                                                                                                                                       |
| Author       | Engineering Team                                                                                                                                                                                                 |
| Parent       | [PRD-001](PRD-001-master-overview.md)                                                                                                                                                                            |
| Related Docs | [PRD-007](PRD-007-developer-tooling.md) (forbidden patterns), [PRD-008-1](PRD-008-1-auth-impl-spec.md) (auth DI), [PRD-011](PRD-011-metrics-collection.md) (metrics setup), [PRD-003](PRD-003-langgraph-orchestration.md) (orchestration) |

---

## §1 — Purpose & Scope

### Problem Statement

Multiple PRDs (PRD-003, PRD-006, PRD-008, PRD-011) already use FastAPI `Depends()` correctly
for Redis, settings, and user auth. However no document defines the **rules** — what is forbidden,
how files are structured, how ARQ workers wire deps, and how tests override them.

Anti-patterns observed in the codebase that cause subtle bugs and untestable code:

- **Nullable DI params** — `AsyncSession | None` as a dep type silently masks misconfiguration;
  the route proceeds with `None` and fails later with an `AttributeError` far from the source.
- **`x = x or SomeClass()` fallback construction** — hides the fact that the dependency was never
  injected and creates an untracked singleton at an unpredictable moment.
- **God `dependencies.py` files** — violates SRP; one change to auth logic requires touching the
  same file as Redis plumbing.
- **Module-level singletons** — `redis_pool = create_pool_sync(...)` at import time prevents test
  isolation and crashes the importer if the service is unavailable.
- **`app.state` accessed directly in routes** — bypasses DI, making the route untestable in
  isolation and coupling it to the application object.
- **ARQ worker deps as globals** — `global worker_redis` inside `on_startup` creates invisible
  state that cannot be inspected, overridden, or garbage-collected cleanly.

### Boundary

This PRD defines DI rules and patterns for all FastAPI routes and ARQ worker tasks.
[PRD-008-1](PRD-008-1-auth-impl-spec.md) defines auth DI (`get_current_user`, token validation)
specifically.

---

## §2 — Core Forbidden Patterns

These five rules are **code-review enforced** — no `ruff` rule catches all of them.
Each subsection shows the forbidden pattern and the correct replacement.

### Rule 1 — No Nullable Dependency Parameters

A dependency provider must never return `None`. If the resource is not ready, the provider raises —
explicitly and immediately — so the error surfaces at the correct layer.

```python
# FORBIDDEN — nullable dep silently passes None into the route
async def get_db(request: Request) -> AsyncSession | None:
    if request.app.state.db_pool:
        return AsyncSession(request.app.state.db_pool)
    return None

async def endpoint(db: Annotated[AsyncSession | None, Depends(get_db)]) -> ...:
    db.execute(...)  # AttributeError: 'NoneType' object has no attribute 'execute'
```

```python
# CORRECT — dep provider raises if not ready; route signature is non-optional
async def get_db(request: Request) -> AsyncSession:
    pool = request.app.state.db_pool   # AttributeError here, at the dep boundary
    async with AsyncSession(pool) as session:
        yield session
```

### Rule 2 — No `x = x or SomeClass()` Conditional Fallback Construction

Fallback construction is forbidden at every layer: dependency providers, factory functions, and
`__init__` bodies. If a dependency was not injected, that is always a programming error — it must
not be silently papered over.

```python
# FORBIDDEN — at any layer
async def get_redis(redis: Redis | None = None) -> Redis:
    redis = redis or await create_pool(RedisSettings())   # hidden singleton, untestable
    return redis

class JobService:
    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis or create_pool_sync(RedisSettings())   # FORBIDDEN
```

```python
# CORRECT — always injected, never conditionally constructed
async def get_redis(request: Request) -> Redis:
    return request.app.state.redis   # set in lifespan; AttributeError if not set
```

### Rule 3 — SRP: One Dependency Module per Resource

A single `dependencies.py` with every dep in the project is a violation of the Single
Responsibility Principle. Any change to auth logic forces a re-review of the Redis plumbing in
the same file.

```python
# FORBIDDEN — god file
# agentops/dependencies.py
async def get_redis(request: Request) -> Redis: ...
async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]: ...
def get_settings() -> Settings: ...
async def get_current_user(token: str, redis: Redis) -> User: ...
async def get_job_and_verify_owner(job_id: str, user: User, db: AsyncSession) -> Job: ...
async def get_meter_provider(request: Request) -> MeterProvider: ...
```

```python
# CORRECT — one file per concern
# agentops/deps/redis.py      → get_redis,              RedisDep
# agentops/deps/db.py         → get_db_session,         DbSessionDep
# agentops/deps/settings.py   → get_settings,           SettingsDep
# agentops/deps/auth.py       → get_current_user,       CurrentUserDep
#                             → get_job_and_verify_owner
# agentops/deps/metrics.py    → get_meter_provider,     MeterProviderDep
```

### Rule 4 — No Module-Level Singletons: All Stateful Resources Live in Lifespan

Module-level instantiation of stateful resources (pools, connections, engines) crashes the
importer when the external service is unavailable, and prevents test isolation entirely.

```python
# FORBIDDEN — module-level instantiation
langsmith_client = Client()            # module-level
redis_pool = create_pool_sync(...)     # FORBIDDEN: stateful, blocks at import
engine = create_async_engine(...)      # FORBIDDEN: stateful, crashes importer without DB
```

```python
# CORRECT — lifespan owns all singleton resources
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    app.state.redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    app.state.db_engine = create_async_engine(settings.database_url)
    app.state.langsmith = Client()   # no cleanup needed
    configure_api_metrics(port=8001)   # PRD-011
    yield
    await app.state.redis.close()
    await app.state.db_engine.dispose()
```

All resources — stateless or stateful — live in `lifespan` (FastAPI) or `on_startup` (ARQ).
No module-level instantiation, no exceptions.

### Rule 5 — No Quasi-Globals in Async Context: ARQ Worker Uses `ctx` Exclusively

`ContextVar` used as a quasi-global and module-level mutable state assigned in `on_startup` are
both forbidden. The ARQ `ctx` dict is the canonical and only carrier for worker-scoped resources.

```python
# FORBIDDEN — ContextVar quasi-global
_redis_var: ContextVar[Redis] = ContextVar("redis")

async def on_startup(ctx: dict) -> None:
    _redis_var.set(await create_pool(RedisSettings()))

async def run_triage(ctx: dict, job_id: str) -> None:
    redis = _redis_var.get()   # invisible dependency on global state
```

```python
# FORBIDDEN — module-level mutable assigned at startup
worker_redis: Redis | None = None

async def on_startup(ctx: dict) -> None:
    global worker_redis
    worker_redis = await create_pool(RedisSettings())

async def run_triage(ctx: dict, job_id: str) -> None:
    assert worker_redis is not None   # None-checks spread through every task
    redis = worker_redis
```

```python
# CORRECT — everything via ctx dict; tasks declare their deps explicitly
async def on_startup(ctx: dict) -> None:
    settings = get_settings()
    ctx["redis"] = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    ctx["db_engine"] = create_async_engine(settings.database_url)

async def run_triage(ctx: dict, job_id: str) -> None:
    redis: Redis = ctx["redis"]
    db_engine = ctx["db_engine"]
    async with AsyncSession(db_engine) as db:
        ...
```

---

## §3 — FastAPI DI Architecture

### Lifespan Pattern (Canonical)

All application-scoped singletons are initialized in `lifespan` and stored in `app.state`.
The lifespan function lives in its own module — `agentops/lifespan.py` — not in the main
`app.py` entrypoint.

```python
# agentops/lifespan.py
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from redis.asyncio import Redis
from arq.connections import RedisSettings, create_pool
from sqlalchemy.ext.asyncio import create_async_engine

from agentops.config import get_settings
from agentops.metrics.setup import configure_api_metrics


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize and clean up all application-scoped singleton resources."""
    settings = get_settings()
    app.state.redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    app.state.db_engine = create_async_engine(settings.database_url)
    configure_api_metrics(port=8001)   # PRD-011: Prometheus scrape endpoint
    yield
    await app.state.redis.close()
    await app.state.db_engine.dispose()
```

### Dependency Provider Files

`agentops/deps/redis.py`:

```python
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis


async def get_redis(request: Request) -> Redis:
    """Return the application Redis pool from app.state."""
    return request.app.state.redis


RedisDep = Annotated[Redis, Depends(get_redis)]
```

`agentops/deps/db.py`:

```python
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a per-request SQLAlchemy async session with rollback on error."""
    async with AsyncSession(request.app.state.db_engine) as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
```

`agentops/deps/settings.py`:

```python
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from agentops.config import Settings


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
```

`agentops/deps/auth.py` (abbreviated — full spec in PRD-008-1):

```python
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentops.deps.redis import RedisDep
from agentops.models import User

_bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    redis: RedisDep,
) -> User:
    """Validate the bearer token and return the authenticated user."""
    ...


CurrentUserDep = Annotated[User, Depends(get_current_user)]
```

`agentops/deps/metrics.py`:

```python
from typing import Annotated

from fastapi import Depends, Request
from opentelemetry.metrics import MeterProvider


async def get_meter_provider(request: Request) -> MeterProvider:
    """Return the application MeterProvider from app.state."""
    return request.app.state.meter_provider


MeterProviderDep = Annotated[MeterProvider, Depends(get_meter_provider)]
```

### `deps/__init__.py` — Re-exports Only Type Aliases

```python
# agentops/deps/__init__.py
# Re-exports Annotated type aliases only.
# Routes import from agentops.deps, not from individual sub-modules.
from agentops.deps.auth import CurrentUserDep
from agentops.deps.db import DbSessionDep
from agentops.deps.metrics import MeterProviderDep
from agentops.deps.redis import RedisDep
from agentops.deps.settings import SettingsDep

__all__ = [
    "CurrentUserDep",
    "DbSessionDep",
    "MeterProviderDep",
    "RedisDep",
    "SettingsDep",
]
```

Provider functions (`get_redis`, `get_db_session`, etc.) are **never** re-exported from
`__init__.py`. Routes that need to override a specific provider import directly from the
sub-module (e.g., `from agentops.deps.redis import get_redis`).

### Route Consumption (Canonical)

```python
from agentops.deps import CurrentUserDep, DbSessionDep, RedisDep

from agentops.models import CreateJobRequest, JobResponse


@router.post("/jobs/")
async def create_job(
    body: CreateJobRequest,
    current_user: CurrentUserDep,
    redis: RedisDep,
    db: DbSessionDep,
) -> JobResponse:
    """Create a new triage job for the authenticated user."""
    ...
```

### Router-Level Auth Injection (Keep Existing Pattern)

When an entire router requires authentication, inject `get_current_user` at the router level
rather than repeating it in every route:

```python
from fastapi import APIRouter, Depends

from agentops.deps.auth import get_current_user

router = APIRouter(
    prefix="/jobs",
    dependencies=[Depends(get_current_user)],
)
```

Individual routes on this router do not redeclare `CurrentUserDep` unless they need the `User`
object for their own logic.

---

## §4 — Async Resource Lifecycle Rules

| Resource Type         | Initialization                      | Cleanup                      | Scope       |
|-----------------------|-------------------------------------|------------------------------|-------------|
| DB connection pool    | `lifespan`                          | `lifespan`                   | Application |
| Redis pool            | `lifespan`                          | `lifespan`                   | Application |
| DB session            | `yield` dep (`get_db_session`)      | `finally` in `yield` dep     | Request     |
| Redis connection      | Return pool from `get_redis`        | Pool manages connections      | Request     |
| Settings              | `@lru_cache` on `get_settings()`    | N/A (immutable)               | Application |
| OTel MeterProvider    | `configure_api_metrics()` in lifespan | N/A                         | Application |

**Rules:**

1. **Application-scoped singletons** — always initialized in `lifespan`, stored in `app.state`.
   Never initialized at import time.
2. **Request-scoped resources** — always via `yield` dependency with `try/finally` ensuring
   cleanup even on exception.
3. **Never mix scopes** — do not create a per-request resource inside lifespan, or vice versa.
4. **Cleanup order** — FastAPI resolves deps in declaration order and cleans up in reverse (LIFO).
   Last-declared dep cleans up first. Keep this in mind when deps depend on each other.

---

## §5 — ARQ Worker DI

The ARQ worker is a separate OS process from the FastAPI API — it has no `app.state` or
`request` object. The `ctx` dict is the only mechanism for passing resources between
`on_startup` / `on_shutdown` and task functions.

```python
# agentops/worker.py
from arq.connections import RedisSettings, create_pool
from sqlalchemy.ext.asyncio import create_async_engine

from agentops.config import get_settings
from agentops.metrics.setup import configure_worker_metrics
from agentops.tasks.triage import run_triage
from agentops.tasks.codebase import build_codebase_index, update_codebase_index


async def on_startup(ctx: dict) -> None:
    """Initialize all worker-scoped resources into ctx."""
    settings = get_settings()
    ctx["redis"] = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    ctx["db_engine"] = create_async_engine(settings.database_url)
    configure_worker_metrics(port=8002)   # PRD-011: worker Prometheus endpoint


async def on_shutdown(ctx: dict) -> None:
    """Clean up all worker-scoped resources from ctx."""
    await ctx["redis"].close()
    await ctx["db_engine"].dispose()


class WorkerSettings:
    """ARQ worker configuration."""

    on_startup = on_startup
    on_shutdown = on_shutdown
    functions = [run_triage, build_codebase_index, update_codebase_index]
    redis_settings = RedisSettings(host="localhost", port=6379)
```

Worker task functions receive all dependencies exclusively from `ctx`:

```python
# agentops/tasks/triage.py
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def run_triage(ctx: dict, job_id: str) -> None:
    """Execute triage pipeline for the given job.

    Args:
        ctx: ARQ context dict containing redis and db_engine.
        job_id: UUID of the job to triage.
    """
    redis: Redis = ctx["redis"]
    db_engine: AsyncEngine = ctx["db_engine"]
    async with AsyncSession(db_engine) as db:
        ...
```

Type annotations on `ctx` values (`redis: Redis = ctx["redis"]`) are documentation — they are
not enforced at runtime. Keep them accurate and update them when `on_startup` changes.

---

## §6 — Dependency Module File Layout

```
agentops/
  deps/
    __init__.py        # re-exports Annotated type aliases only (RedisDep, DbSessionDep, ...)
    redis.py           # get_redis,              RedisDep
    db.py              # get_db_session,         DbSessionDep
    settings.py        # get_settings,           SettingsDep
    auth.py            # get_current_user,       CurrentUserDep
                       # get_job_and_verify_owner
    metrics.py         # get_meter_provider,     MeterProviderDep
  lifespan.py          # lifespan context manager — wires resources into app.state
  config.py            # Settings(BaseSettings) — single source of env vars
  worker.py            # on_startup, on_shutdown, WorkerSettings
  tasks/
    triage.py          # run_triage
    codebase.py        # build_codebase_index, update_codebase_index
```

**Layout rules:**

- Each `deps/*.py` file contains exactly one resource's provider function(s) and the
  corresponding `Annotated` type alias.
- `deps/__init__.py` re-exports only `Annotated` type aliases — never provider functions.
- Routes import type aliases from `agentops.deps` (the package), not from sub-modules.
- `lifespan.py` is the only file that writes to `app.state`.
- `worker.py` is the only file that writes to the `ctx` dict (other than task functions reading
  from it).

---

## §7 — Testing with DI

### Override Pattern (FastAPI Built-in)

FastAPI's `dependency_overrides` dict replaces a provider function for the duration of a test.
This is the only permitted way to inject test doubles — never patch module-level globals.

```python
# tests/conftest.py
import pytest
from fakeredis.aioredis import FakeRedis

from agentops.deps.redis import get_redis
from agentops.deps.db import get_db_session
from agentops.main import app


@pytest.fixture
def fake_redis() -> FakeRedis:
    """In-memory Redis substitute for tests."""
    return FakeRedis()


@pytest.fixture
def app_with_redis(fake_redis: FakeRedis):
    """App with Redis overridden to use FakeRedis."""
    app.dependency_overrides[get_redis] = lambda: fake_redis
    yield app
    app.dependency_overrides.clear()
```

### DB Session Override

```python
# tests/conftest.py (continued)
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from agentops.deps.db import get_db_session
from agentops.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_engine():
    """In-memory SQLite engine for test isolation."""
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_db_session(test_engine):
    """Per-test database session with automatic rollback."""
    async with AsyncSession(test_engine) as session:
        yield session


@pytest.fixture
def app_with_db(test_db_session: AsyncSession):
    """App with DB session overridden to the test session."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session
    yield app
    app.dependency_overrides.clear()
```

### Combining Multiple Overrides

```python
@pytest.fixture
def app_with_all_overrides(fake_redis: FakeRedis, test_db_session: AsyncSession):
    """App with both Redis and DB overridden for integration-style unit tests."""
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_session] = lambda: test_db_session
    yield app
    app.dependency_overrides.clear()
```

### Rule

Never use `monkeypatch` or `unittest.mock.patch` to replace module-level variables in tests.
`dependency_overrides` is the only permitted override mechanism. This is only possible because
rules 3–4 above ensure no module-level singletons exist — there is nothing to patch.

---

## §8 — Cross-References

| Document | Relevance |
|---|---|
| [PRD-007 — Developer Tooling](PRD-007-developer-tooling.md) | Forbidden patterns: `isinstance`, `cast`, `TYPE_CHECKING`, try-catch spam, `Any` |
| [PRD-008-1 — Auth Implementation Spec](PRD-008-1-auth-impl-spec.md) | `get_current_user`, `get_redis` usage in the auth layer; token validation flow |
| [PRD-011 — Metrics Collection](PRD-011-metrics-collection.md) | `configure_api_metrics()` and `configure_worker_metrics()` called from lifespan / `on_startup` |
| [PRD-003 — LangGraph Orchestration](PRD-003-langgraph-orchestration.md) | `graph.aget_state()` / `graph.update_state()` take no deps — pure functions; lifespan canonical pattern |
| [PRD-006 — Data Validation](PRD-006-data-validation.md) | Pydantic `BaseModel` used for request/response bodies injected alongside DI params |
