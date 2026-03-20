"""GraphQL schema — Query, Mutation, Subscription resolvers + context getter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import redis.asyncio as aioredis
import strawberry
from arq import ArqRedis
from fastapi import Depends, Request, Response
from starlette.requests import HTTPConnection
from strawberry.fastapi import GraphQLRouter
from strawberry.subscriptions import GRAPHQL_TRANSPORT_WS_PROTOCOL

from agentops.api.deps.arq import get_arq
from agentops.api.deps.auth import resolve_user_from_token
from agentops.api.deps.redis import get_redis
from agentops.config import Settings, get_settings
from agentops.github.client import fetch_issue, parse_issue_url
from agentops.github.writeback import post_triage_comment
from agentops.graphql.context import GraphQLContext
from agentops.graphql.types import (
    CreateJobInput,
    CreateJobResult,
    DeleteTokenResult,
    Job,
    JobActionResult,
    JobEvent,
    JobSnapshotEvent,
    LogoutResult,
    PostCommentResult,
    UserInfo,
    event_from_dict,
)
from agentops.models.job import TERMINAL_STATUSES, JobData

_logger = logging.getLogger(__name__)

_GITHUB_ISSUE_URL_PATTERN = r"^https://github\.com/[^/]+/[^/]+/issues/\d+$"
_MAX_ACTIVE_JOBS_PER_OWNER = 10
_ARQ_ABORT_SS = "arq:abort"
_ARQ_RESULT_PREFIX = "arq:result:"


# ── Helpers ────────────────────────────────────────────────────────────


async def _abort_arq_job(redis: aioredis.Redis, job_id: str) -> None:
    """Signal the arq worker to abort a job (fire-and-forget)."""
    await redis.zadd(_ARQ_ABORT_SS, {job_id: int(time.time() * 1000)})


async def _clear_arq_result(redis: aioredis.Redis, job_id: str) -> None:
    """Remove a stale arq result so a new job with the same ID can be enqueued."""
    await redis.delete(f"{_ARQ_RESULT_PREFIX}{job_id}")


def _extract_bearer_token(connection: HTTPConnection) -> str | None:
    """Extract Bearer token from Authorization header, if present."""
    auth = connection.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _job_from_dict(data: JobData) -> Job:
    return Job(
        job_id=strawberry.ID(data.job_id),
        status=data.status,
        issue_url=data.issue_url,
        issue_title=data.issue_title,
        repository=data.repository,
        langsmith_url=data.langsmith_url,
        awaiting_human=data.awaiting_human,
        current_node=data.current_node,
        created_at=data.created_at,
        pending_question=data.pending_question,
        pending_question_context=data.pending_question_context,
        github_comment_url=data.github_comment_url,
        severity=data.severity,
        recommended_fix=data.recommended_fix,
        github_comment=data.github_comment,
        relevant_files=data.relevant_files,
        ticket_title=data.ticket_title,
    )


async def _load_job_data(redis: aioredis.Redis, job_id: str) -> JobData:
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise ValueError(f"Job {job_id} not found")
    return JobData.model_validate_json(raw)


# ── Query ──────────────────────────────────────────────────────────────


@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: strawberry.Info[GraphQLContext]) -> UserInfo:
        return _require_user(info)

    @strawberry.field
    async def job(self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID) -> Job:
        data = await _load_job_data(info.context["redis"], str(job_id))
        return _job_from_dict(data)

    @strawberry.field
    async def jobs(self, info: strawberry.Info[GraphQLContext]) -> list[Job]:
        redis: aioredis.Redis = info.context["redis"]
        user: UserInfo | None = info.context.get("user")
        owner_id = user.github_id if user else "anonymous"
        result: list[Job] = []
        cursor: int = 0
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match="job:*", count=100)
            for key in keys:
                raw = await redis.get(key)
                if raw is None:
                    continue
                data = JobData.model_validate_json(raw)
                if data.owner_id == owner_id:
                    result.append(_job_from_dict(data))
            if cursor == 0:
                break
        return result


# ── Mutation ───────────────────────────────────────────────────────────


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_job(
        self, info: strawberry.Info[GraphQLContext], input: CreateJobInput
    ) -> CreateJobResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        user: UserInfo | None = info.context.get("user")
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

        data = JobData(
            job_id=job_id,
            status="queued",
            issue_url=input.issue_url,
            issue_title=issue_title,
            issue_body=issue_body,
            repository=repository,
            supervisor_notes=input.supervisor_notes,
            owner_id=owner_id,
            created_at=datetime.now(UTC).isoformat(),
        )
        await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

        # Auto-index repository if not already indexed
        if repository:
            index_guard = await redis.set(f"repo_index:{repository}", "building", nx=True, ex=86400)
            if index_guard is not None:
                await arq.enqueue_job(
                    "build_codebase_index", repository, _job_id=f"index:{repository}"
                )

        await arq.enqueue_job("run_triage", job_id, _job_id=job_id)

        return CreateJobResult(job_id=strawberry.ID(job_id), status="queued")

    @strawberry.mutation
    async def kill_job(
        self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID
    ) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        data = await _load_job_data(redis, str(job_id))

        if data.status in TERMINAL_STATUSES:
            return JobActionResult(status=data.status, job_id=job_id)

        await _abort_arq_job(redis, str(job_id))

        data.status = "killed"
        await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
        await redis.publish(f"jobs:{job_id}:events", json.dumps({"type": "job.killed"}))

        await redis.decr(f"active_jobs:{data.owner_id or 'anonymous'}")

        return JobActionResult(status="killed", job_id=job_id)

    @strawberry.mutation
    async def answer_job(
        self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID, answer: str
    ) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        data = await _load_job_data(redis, str(job_id))

        if not data.awaiting_human:
            raise ValueError("Job is not awaiting human input")

        await _abort_arq_job(redis, f"timeout:{job_id}")

        data.awaiting_human = False
        data.status = "running"
        await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
        await _clear_arq_result(redis, str(job_id))
        await arq.enqueue_job("resume_graph", str(job_id), answer, _job_id=str(job_id))

        return JobActionResult(status="answer_received", job_id=job_id)

    @strawberry.mutation
    async def pause_job(
        self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID
    ) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        data = await _load_job_data(redis, str(job_id))

        data.status = "pausing"
        data.paused = True
        await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

        return JobActionResult(status="pausing", job_id=job_id)

    @strawberry.mutation
    async def resume_job(
        self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID
    ) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        data = await _load_job_data(redis, str(job_id))

        data.status = "running"
        data.paused = False
        await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
        await _clear_arq_result(redis, str(job_id))
        await arq.enqueue_job("resume_graph", str(job_id), "resume", _job_id=str(job_id))

        return JobActionResult(status="resumed", job_id=job_id)

    @strawberry.mutation
    async def redirect_job(
        self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID, instruction: str
    ) -> JobActionResult:
        redis: aioredis.Redis = info.context["redis"]
        arq: ArqRedis = info.context["arq"]
        data = await _load_job_data(redis, str(job_id))

        data.redirect_instructions.append(instruction)

        if data.paused:
            data.paused = False
            data.status = "running"
            await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
            await _clear_arq_result(redis, str(job_id))
            await arq.enqueue_job(
                "resume_graph",
                str(job_id),
                json.dumps({"type": "redirect", "instruction": instruction}),
                True,
                _job_id=str(job_id),
            )
        else:
            await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

        return JobActionResult(status="redirected", job_id=job_id)

    @strawberry.mutation
    async def post_comment(
        self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID
    ) -> PostCommentResult:
        user = _require_user(info)
        settings: Settings = info.context["settings"]
        comment_url = await post_triage_comment(
            info.context["redis"], str(job_id), user.github_id, settings
        )
        return PostCommentResult(ok=True, comment_url=comment_url)

    @strawberry.mutation
    async def logout(self, info: strawberry.Info[GraphQLContext]) -> LogoutResult:
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
    async def delete_github_token(self, info: strawberry.Info[GraphQLContext]) -> DeleteTokenResult:
        user = _require_user(info)
        redis: aioredis.Redis = info.context["redis"]
        await redis.delete(f"github_token:{user.github_id}")
        return DeleteTokenResult(ok=True)


# ── Subscription ───────────────────────────────────────────────────────


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def job_events(
        self, info: strawberry.Info[GraphQLContext], job_id: strawberry.ID
    ) -> AsyncGenerator[JobEvent, None]:
        redis: aioredis.Redis = info.context["redis"]
        pubsub = redis.pubsub()
        channel = f"jobs:{job_id}:events"

        # Subscribe FIRST — Redis buffers messages from this point
        await pubsub.subscribe(channel)

        try:
            # Yield current state as snapshot (catches up on anything before subscribe)
            raw = await redis.get(f"job:{job_id}")
            if raw is not None:
                data = JobData.model_validate_json(raw)
                yield JobSnapshotEvent(
                    status=data.status,
                    current_node=data.current_node,
                    awaiting_human=data.awaiting_human,
                    pending_question=data.pending_question,
                    pending_question_context=data.pending_question_context,
                )
                if data.status in TERMINAL_STATUSES:
                    return

            # Yield live events (including any buffered during snapshot fetch)
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                parsed = json.loads(message["data"])
                event = event_from_dict(parsed)
                if event is None:
                    continue
                yield event
                if parsed.get("type", "") in (
                    "job.done",
                    "job.failed",
                    "job.killed",
                    "job.timed_out",
                ):
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


# ── Schema + Router ────────────────────────────────────────────────────

schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)


def _require_user(info: strawberry.Info[GraphQLContext]) -> UserInfo:
    """Raise if no authenticated user in context."""
    user: UserInfo | None = info.context.get("user")
    if user is None:
        raise PermissionError("Authentication required")
    return user


async def get_context(
    connection: HTTPConnection,
    redis: aioredis.Redis = Depends(get_redis),
    arq: ArqRedis = Depends(get_arq),
    settings: Settings = Depends(get_settings),
) -> GraphQLContext:
    """Build context for both HTTP and WebSocket.

    Auth for HTTP: extracted from Authorization header.
    Auth for WebSocket: handled in on_ws_connect via connectionParams.
    """
    ctx: GraphQLContext = {
        "redis": redis,
        "arq": arq,
        "settings": settings,
    }

    if connection.scope["type"] == "http":
        ctx["request"] = connection  # type: ignore[assignment]
        ctx["response"] = Response()
        token = _extract_bearer_token(connection)
        if token:
            ctx["user"] = await resolve_user_from_token(token, settings, redis)

    return ctx


class _AuthGraphQLRouter(GraphQLRouter):
    async def on_ws_connect(  # type: ignore[override]
        self, context: GraphQLContext
    ) -> None:
        params: dict[str, str] = context.get("connection_params") or {}
        auth_value = params.get("Authorization", "")
        if auth_value.startswith("Bearer "):
            token = auth_value[7:]
            redis: aioredis.Redis = context["redis"]
            settings: Settings = context["settings"]
            user = await resolve_user_from_token(token, settings, redis)
            context["user"] = user


graphql_app = _AuthGraphQLRouter(
    schema,
    context_getter=get_context,  # type: ignore[arg-type]
    subscription_protocols=[GRAPHQL_TRANSPORT_WS_PROTOCOL],
)
