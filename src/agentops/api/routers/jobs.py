import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentops.api.deps.arq import ArqDep
from agentops.api.deps.auth import CurrentUserDep, OptionalUserDep
from agentops.api.deps.redis import RedisDep
from agentops.config import Settings, get_settings
from agentops.github.client import fetch_issue, parse_issue_url
from agentops.github.writeback import post_triage_comment
from agentops.models.job import TERMINAL_STATUSES, JobData

SettingsDep = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/jobs", tags=["jobs"])

_logger = logging.getLogger(__name__)

_GITHUB_ISSUE_URL_PATTERN = r"^https://github\.com/[^/]+/[^/]+/issues/\d+$"
_MAX_ACTIVE_JOBS_PER_OWNER = 10
_SSE_KEEPALIVE_SECONDS = 30

GitHubIssueUrl = Annotated[str, Field(pattern=_GITHUB_ISSUE_URL_PATTERN)]


class CreateJobRequest(BaseModel):
    issue_url: GitHubIssueUrl
    supervisor_notes: str = ""


class CreateJobResponse(BaseModel):
    job_id: str
    status: str = "queued"


class JobResponse(BaseModel):
    job_id: str
    status: str
    issue_url: str
    issue_title: str = ""
    repository: str = ""
    langsmith_url: str = ""
    awaiting_human: bool = False
    current_node: str = ""
    created_at: str = ""


class AnswerRequest(BaseModel):
    answer: str


class RedirectRequest(BaseModel):
    instruction: str


class FeedbackRequest(BaseModel):
    key: str
    score: float
    comment: str = ""


class JobActionResponse(BaseModel):
    status: str
    job_id: str


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CreateJobResponse)
async def create_job(
    body: CreateJobRequest,
    redis: RedisDep,
    arq: ArqDep,
    current_user: OptionalUserDep,
) -> CreateJobResponse:
    """Create a new triage job. Idempotent within 24h per issue URL."""
    owner_id = current_user.github_id if current_user else "anonymous"
    active_key = f"active_jobs:{owner_id}"

    # Idempotency key
    idempotency_key = (
        f"idempotency:{hashlib.sha256(f'{body.issue_url}{owner_id}'.encode()).hexdigest()}"
    )

    job_id = str(uuid.uuid4())
    set_result = await redis.set(idempotency_key, job_id, nx=True, ex=86400)
    if set_result is None:
        existing_job_id = await redis.get(idempotency_key)
        return CreateJobResponse(job_id=existing_job_id or job_id, status="queued")

    # Atomic rate-limit: INCR first, then check
    new_count: int = await redis.incr(active_key)
    if new_count == 1:
        await redis.expire(active_key, 86400)
    if new_count > _MAX_ACTIVE_JOBS_PER_OWNER:
        await redis.decr(active_key)
        await redis.delete(idempotency_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Active job limit ({_MAX_ACTIVE_JOBS_PER_OWNER}) exceeded",
        )

    # Fetch issue metadata from GitHub (best-effort)
    issue_title = ""
    issue_body = ""
    repository = ""
    parsed = parse_issue_url(body.issue_url)
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
        issue_url=body.issue_url,
        issue_title=issue_title,
        issue_body=issue_body,
        repository=repository,
        supervisor_notes=body.supervisor_notes,
        owner_id=owner_id,
    )
    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

    # Auto-index repository if not already indexed
    if repository:
        index_guard = await redis.set(f"repo_index:{repository}", "building", nx=True, ex=86400)
        if index_guard is not None:
            await arq.enqueue_job("build_codebase_index", repository, _job_id=f"index:{repository}")

    await arq.enqueue_job("run_triage", job_id, _job_id=job_id)

    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, redis: RedisDep) -> JobResponse:
    """Get job status and details."""
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse.model_validate(json.loads(raw))


async def _sse_generator(redis: RedisDep, job_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to Redis Pub/Sub and yield SSE-formatted events."""
    pubsub = redis.pubsub()
    channel = f"jobs:{job_id}:events"
    await pubsub.subscribe(channel)
    seq = 0

    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=_SSE_KEEPALIVE_SECONDS
                    ),
                    timeout=_SSE_KEEPALIVE_SECONDS + 5,
                )
            except TimeoutError:
                yield ":keepalive\n\n"
                continue

            if message is None:
                # Send keepalive comment
                yield ":keepalive\n\n"
                continue

            data = message["data"]
            seq += 1
            yield f"id: {seq}\ndata: {data}\n\n"

            # Break on terminal events
            parsed = json.loads(data)
            event_type = parsed.get("type", "")
            if event_type in ("job.done", "job.failed", "job.killed", "job.timed_out"):
                break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


@router.get("/{job_id}/stream")
async def stream_job(job_id: str, redis: RedisDep) -> StreamingResponse:
    """Stream SSE events for a job via Redis Pub/Sub."""
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        _sse_generator(redis, job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _load_job_data(redis: RedisDep, job_id: str) -> JobData:
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobData.model_validate_json(raw)


@router.post("/{job_id}/answer", response_model=JobActionResponse)
async def answer_job(
    job_id: str,
    body: AnswerRequest,
    redis: RedisDep,
    arq: ArqDep,
) -> JobActionResponse:
    """Resume a job waiting for human input by providing an answer."""
    data = await _load_job_data(redis, job_id)

    if not data.awaiting_human:
        raise HTTPException(status_code=409, detail="Job is not awaiting human input")

    await arq.abort_job(f"timeout:{job_id}")

    data.awaiting_human = False
    data.status = "running"
    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

    await arq.enqueue_job("resume_graph", job_id, body.answer, _job_id=job_id)

    return JobActionResponse(status="answer_received", job_id=job_id)


@router.post("/{job_id}/pause", response_model=JobActionResponse)
async def pause_job(
    job_id: str,
    redis: RedisDep,
) -> JobActionResponse:
    """Request a running job to pause at the next supervisor boundary."""
    data = await _load_job_data(redis, job_id)

    if data.status in TERMINAL_STATUSES:
        return JobActionResponse(status=data.status, job_id=job_id)

    data.status = "pausing"
    data.paused = True
    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

    return JobActionResponse(status="pausing", job_id=job_id)


@router.post("/{job_id}/resume", response_model=JobActionResponse)
async def resume_job(
    job_id: str,
    redis: RedisDep,
    arq: ArqDep,
) -> JobActionResponse:
    """Resume a paused job."""
    data = await _load_job_data(redis, job_id)

    if data.status in TERMINAL_STATUSES:
        return JobActionResponse(status=data.status, job_id=job_id)
    if not data.paused:
        raise HTTPException(status_code=409, detail="Job is not paused")

    data.status = "running"
    data.paused = False
    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

    await arq.enqueue_job("resume_graph", job_id, "resume", _job_id=job_id)

    return JobActionResponse(status="resumed", job_id=job_id)


@router.post("/{job_id}/redirect", response_model=JobActionResponse)
async def redirect_job(
    job_id: str,
    body: RedirectRequest,
    redis: RedisDep,
    arq: ArqDep,
) -> JobActionResponse:
    """Inject a redirect instruction into a running or paused job."""
    data = await _load_job_data(redis, job_id)

    data.redirect_instructions.append(body.instruction)

    if data.paused:
        data.paused = False
        data.status = "running"
        await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
        await arq.enqueue_job(
            "resume_graph",
            job_id,
            json.dumps({"type": "redirect", "instruction": body.instruction}),
            True,
            _job_id=job_id,
        )
    else:
        await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

    return JobActionResponse(status="redirected", job_id=job_id)


@router.delete("/{job_id}", response_model=JobActionResponse)
async def kill_job(
    job_id: str,
    redis: RedisDep,
    arq: ArqDep,
) -> JobActionResponse:
    """Kill a running job."""
    data = await _load_job_data(redis, job_id)

    if data.status in TERMINAL_STATUSES:
        return JobActionResponse(status=data.status, job_id=job_id)

    # Abort the ARQ task
    await arq.abort_job(job_id)

    data.status = "killed"
    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())
    await redis.publish(f"jobs:{job_id}:events", json.dumps({"type": "job.killed"}))

    await redis.decr(f"active_jobs:{data.owner_id or 'anonymous'}")

    return JobActionResponse(status="killed", job_id=job_id)


@router.post("/{job_id}/post-comment")
async def post_github_comment(
    job_id: str,
    redis: RedisDep,
    current_user: CurrentUserDep,
    settings: SettingsDep,
) -> dict[str, str]:
    """Post triage report as GitHub comment."""
    comment_url = await post_triage_comment(redis, job_id, current_user.github_id, settings)
    return {"status": "comment_posted", "job_id": job_id, "comment_url": comment_url}


@router.post("/{job_id}/create-ticket")
async def create_github_ticket(job_id: str, redis: RedisDep) -> dict[str, str]:
    """Create GitHub issue from ticket draft. Full implementation uses DB token."""
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ticket_created", "job_id": job_id}


@router.post("/{job_id}/feedback")
async def submit_job_feedback(
    job_id: str,
    body: FeedbackRequest,
    redis: RedisDep,
) -> dict[str, str]:
    """Submit LangSmith feedback for a job."""
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    data = json.loads(raw)
    run_id = data.get("langsmith_run_id", "")
    settings = get_settings()
    if run_id and settings.langsmith_api_key:
        from agentops.langsmith_handler import LangSmithFeedbackHandler

        handler = LangSmithFeedbackHandler(
            api_key=settings.langsmith_api_key,
            org_id=settings.langsmith_org_id,
            project_id=settings.langsmith_project_id,
        )
        await asyncio.to_thread(handler.submit_feedback, run_id, body.key, body.score, body.comment)
    return {"status": "feedback_submitted", "job_id": job_id}
