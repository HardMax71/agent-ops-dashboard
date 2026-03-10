"""GraphQL schema — Query, Mutation, Subscription resolvers + context getter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import redis.asyncio as aioredis
import strawberry
from arq import ArqRedis
from fastapi import Depends, Request, Response
from strawberry.fastapi import GraphQLRouter
from strawberry.subscriptions import GRAPHQL_TRANSPORT_WS_PROTOCOL

from agentops.api.deps.arq import get_arq
from agentops.api.deps.auth import get_optional_user
from agentops.api.deps.redis import get_redis
from agentops.config import Settings, get_settings
from agentops.github.client import fetch_issue, parse_issue_url
from agentops.graphql.types import (
    CreateJobInput,
    CreateJobResult,
    DeleteTokenResult,
    Job,
    JobActionResult,
    JobEvent,
    LogoutResult,
    PostCommentResult,
    UserInfo,
    event_from_dict,
)

_logger = logging.getLogger(__name__)

_GITHUB_ISSUE_URL_PATTERN = r"^https://github\.com/[^/]+/[^/]+/issues/\d+$"
_MAX_ACTIVE_JOBS_PER_OWNER = 10


# ── Helpers ────────────────────────────────────────────────────────────


def _job_from_dict(data: dict[str, str | int | bool | None]) -> Job:
    return Job(
        job_id=strawberry.ID(str(data.get("job_id", ""))),
        status=str(data.get("status", "")),
        issue_url=str(data.get("issue_url", "")),
        issue_title=str(data.get("issue_title", "")),
        repository=str(data.get("repository", "")),
        langsmith_url=str(data.get("langsmith_url", "")),
        awaiting_human=bool(data.get("awaiting_human", False)),
        current_node=str(data.get("current_node", "")),
        created_at=str(data.get("created_at", "")),
    )


async def _load_job_data(redis: aioredis.Redis, job_id: str) -> dict[str, str | int | bool | None]:
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise ValueError(f"Job {job_id} not found")
    return json.loads(raw)


# ── Query ──────────────────────────────────────────────────────────────


@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: strawberry.Info) -> UserInfo:
        return _require_user(info)

    @strawberry.field
    async def job(self, info: strawberry.Info, job_id: strawberry.ID) -> Job:
        redis: aioredis.Redis = info.context["redis"]
        data = await _load_job_data(redis, str(job_id))
        return _job_from_dict(data)


# ── Mutation ───────────────────────────────────────────────────────────


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_job(self, info: strawberry.Info, input: CreateJobInput) -> CreateJobResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        user: UserInfo | None = info.context["user"]
        owner_id = user.github_id if user else "anonymous"
        active_key = f"active_jobs:{owner_id}"

        if not re.match(_GITHUB_ISSUE_URL_PATTERN, input.issue_url):
            raise ValueError("Invalid GitHub issue URL")

        # Idempotency key
        idempotency_key = (
            f"idempotency:{hashlib.sha256(f'{input.issue_url}{owner_id}'.encode()).hexdigest()}"
        )

        job_id = str(uuid.uuid4())
        set_result = await redis.set(idempotency_key, job_id, nx=True, ex=86400)
        if set_result is None:
            existing_job_id = await redis.get(idempotency_key)
            return CreateJobResult(job_id=strawberry.ID(existing_job_id or job_id), status="queued")

        # Atomic rate-limit
        new_count: int = await redis.incr(active_key)
        if new_count == 1:
            await redis.expire(active_key, 86400)
        if new_count > _MAX_ACTIVE_JOBS_PER_OWNER:
            await redis.decr(active_key)
            await redis.delete(idempotency_key)
            raise ValueError(f"Active job limit ({_MAX_ACTIVE_JOBS_PER_OWNER}) exceeded")

        # Fetch issue metadata (best-effort)
        issue_title = ""
        issue_body = ""
        repository = ""
        parsed = parse_issue_url(input.issue_url)
        if parsed is not None:
            owner, repo, number = parsed
            repository = f"{owner}/{repo}"
            issue_data = await fetch_issue(owner, repo, number)
            if issue_data is not None:
                issue_title = issue_data.title
                issue_body = issue_data.body

        job_data = {
            "job_id": job_id,
            "status": "queued",
            "issue_url": input.issue_url,
            "issue_title": issue_title,
            "issue_body": issue_body,
            "repository": repository,
            "supervisor_notes": input.supervisor_notes,
            "langsmith_url": "",
            "awaiting_human": False,
            "current_node": "",
            "owner_id": owner_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await redis.setex(f"job:{job_id}", 86400, json.dumps(job_data))
        await arq.enqueue_job("run_triage", job_id, _job_id=job_id)

        return CreateJobResult(job_id=strawberry.ID(job_id), status="queued")

    @strawberry.mutation
    async def kill_job(self, info: strawberry.Info, job_id: strawberry.ID) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        data = await _load_job_data(redis, str(job_id))

        terminal = frozenset({"killed", "done", "failed", "timed_out"})
        current_status = str(data.get("status", ""))
        if current_status in terminal:
            return JobActionResult(status=current_status, job_id=job_id)

        await arq.abort_job(str(job_id))

        data["status"] = "killed"
        await redis.setex(f"job:{job_id}", 86400, json.dumps(data))
        await redis.publish(f"jobs:{job_id}:events", json.dumps({"type": "job.killed"}))

        owner_id = str(data.get("owner_id", "anonymous"))
        await redis.decr(f"active_jobs:{owner_id}")

        return JobActionResult(status="killed", job_id=job_id)

    @strawberry.mutation
    async def answer_job(
        self, info: strawberry.Info, job_id: strawberry.ID, answer: str
    ) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        data = await _load_job_data(redis, str(job_id))

        if not data.get("awaiting_human"):
            raise ValueError("Job is not awaiting human input")

        await arq.abort_job(f"timeout:{job_id}")

        data["awaiting_human"] = False
        data["status"] = "running"
        await redis.setex(f"job:{job_id}", 86400, json.dumps(data))
        await arq.enqueue_job("resume_graph", str(job_id), answer, _job_id=str(job_id))

        return JobActionResult(status="answer_received", job_id=job_id)

    @strawberry.mutation
    async def pause_job(self, info: strawberry.Info, job_id: strawberry.ID) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        data = await _load_job_data(redis, str(job_id))

        data["status"] = "pausing"
        data["paused"] = True
        await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

        return JobActionResult(status="pausing", job_id=job_id)

    @strawberry.mutation
    async def resume_job(self, info: strawberry.Info, job_id: strawberry.ID) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        data = await _load_job_data(redis, str(job_id))

        data["status"] = "running"
        data["paused"] = False
        await redis.setex(f"job:{job_id}", 86400, json.dumps(data))
        await arq.enqueue_job("resume_graph", str(job_id), "resume", _job_id=str(job_id))

        return JobActionResult(status="resumed", job_id=job_id)

    @strawberry.mutation
    async def redirect_job(
        self, info: strawberry.Info, job_id: strawberry.ID, instruction: str
    ) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        data = await _load_job_data(redis, str(job_id))

        existing = data.get("redirect_instructions")
        instructions: list[str] = [*existing] if existing else []  # type: ignore[misc]
        instructions.append(instruction)
        data["redirect_instructions"] = instructions  # type: ignore[assignment]

        if data.get("paused"):
            data["paused"] = False
            data["status"] = "running"
            await redis.setex(f"job:{job_id}", 86400, json.dumps(data))
            await arq.enqueue_job(
                "resume_graph",
                str(job_id),
                json.dumps({"type": "redirect", "instruction": instruction}),
                True,
                _job_id=str(job_id),
            )
        else:
            await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

        return JobActionResult(status="redirected", job_id=job_id)

    @strawberry.mutation
    async def post_comment(self, info: strawberry.Info, job_id: strawberry.ID) -> PostCommentResult:
        redis: aioredis.Redis = info.context["redis"]
        raw = await redis.get(f"job:{job_id}")
        if raw is None:
            raise ValueError("Job not found")
        raise ValueError("Not implemented")

    @strawberry.mutation
    async def logout(self, info: strawberry.Info) -> LogoutResult:
        user = _require_user(info)
        request: Request = info.context["request"]
        response: Response = info.context["response"]
        redis: aioredis.Redis = info.context["redis"]
        settings: Settings = info.context["settings"]

        await redis.setex(
            f"jti_blacklist:{user.jti}",
            settings.access_token_expire_seconds,
            "1",
        )

        refresh_token_id = request.cookies.get("refresh_token")
        if refresh_token_id:
            await redis.delete(f"refresh_token:{refresh_token_id}")

        response.delete_cookie("refresh_token", path="/auth")
        return LogoutResult(ok=True)

    @strawberry.mutation
    async def delete_github_token(self, info: strawberry.Info) -> DeleteTokenResult:
        user = _require_user(info)
        redis: aioredis.Redis = info.context["redis"]
        await redis.delete(f"github_token:{user.github_id}")
        return DeleteTokenResult(ok=True)


# ── Subscription ───────────────────────────────────────────────────────


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def job_events(
        self, info: strawberry.Info, job_id: strawberry.ID
    ) -> AsyncGenerator[JobEvent, None]:
        redis: aioredis.Redis = info.context["redis"]
        pubsub = redis.pubsub()
        channel = f"jobs:{job_id}:events"
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    event = event_from_dict(data)
                    if event is None:
                        continue
                    yield event
                    event_type = data.get("type", "")
                    if event_type in ("job.done", "job.failed", "job.killed", "job.timed_out"):
                        break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


# ── Schema + Router ────────────────────────────────────────────────────

schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)


def _require_user(info: strawberry.Info) -> UserInfo:
    """Raise if no authenticated user in context."""
    user: UserInfo | None = info.context["user"]
    if user is None:
        raise PermissionError("Authentication required")
    return user


async def get_context(
    request: Request,
    response: Response,
    user: UserInfo | None = Depends(get_optional_user),
    redis: aioredis.Redis = Depends(get_redis),
    arq: ArqRedis = Depends(get_arq),
    settings: Settings = Depends(get_settings),
) -> dict[str, Request | Response | UserInfo | None | aioredis.Redis | ArqRedis | Settings]:
    return {
        "request": request,
        "response": response,
        "user": user,
        "redis": redis,
        "arq": arq,
        "settings": settings,
    }


graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    subscription_protocols=[GRAPHQL_TRANSPORT_WS_PROTOCOL],
)
