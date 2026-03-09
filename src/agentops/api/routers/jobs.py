import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field

from agentops.api.deps.arq import ArqDep
from agentops.api.deps.auth import OptionalUserDep
from agentops.api.deps.graph import GraphDep
from agentops.api.deps.redis import RedisDep
from agentops.github.client import fetch_issue, parse_issue_url

router = APIRouter(prefix="/jobs", tags=["jobs"])

_logger = logging.getLogger(__name__)

_GITHUB_ISSUE_URL_PATTERN = r"^https://github\.com/[^/]+/[^/]+/issues/\d+$"
_MAX_ACTIVE_JOBS_PER_OWNER = 10
_SSE_KEEPALIVE_SECONDS = 30

GitHubIssueUrl = Annotated[str, Field(pattern=_GITHUB_ISSUE_URL_PATTERN)]


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


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
    langsmith_url: str = ""
    awaiting_human: bool = False
    current_node: str = ""


class AnswerRequest(BaseModel):
    answer: str


class RedirectRequest(BaseModel):
    instruction: str


class JobActionResponse(BaseModel):
    status: str
    job_id: str


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CreateJobResponse)
async def create_job(
    body: CreateJobRequest,
    redis: RedisDep,
    arq: ArqDep,
    current_user: OptionalUserDep,
) -> CreateJobResponse:
    """Create a new triage job. Idempotent within 24h per issue URL."""
    owner_id = current_user.github_id if current_user else "anonymous"

    # Rate limiting: max active jobs per owner
    active_key = f"active_jobs:{owner_id}"
    active_count = int(await redis.get(active_key) or "0")
    if active_count >= _MAX_ACTIVE_JOBS_PER_OWNER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Active job limit ({_MAX_ACTIVE_JOBS_PER_OWNER}) exceeded",
        )

    # Idempotency key
    idempotency_key = (
        f"idempotency:{hashlib.sha256(f'{body.issue_url}{owner_id}'.encode()).hexdigest()}"
    )

    job_id = str(uuid.uuid4())
    set_result = await redis.set(idempotency_key, job_id, nx=True, ex=86400)
    if set_result is None:
        existing_job_id = await redis.get(idempotency_key)
        return CreateJobResponse(job_id=existing_job_id or job_id, status="queued")

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

    job_data = {
        "job_id": job_id,
        "status": "queued",
        "issue_url": body.issue_url,
        "issue_title": issue_title,
        "issue_body": issue_body,
        "repository": repository,
        "supervisor_notes": body.supervisor_notes,
        "langsmith_url": "",
        "awaiting_human": False,
        "current_node": "",
        "owner_id": owner_id,
    }
    await redis.setex(f"job:{job_id}", 86400, json.dumps(job_data))

    # Increment active jobs counter
    pipe = redis.pipeline()
    pipe.incr(active_key)
    pipe.expire(active_key, 86400)
    await pipe.execute()

    await arq.enqueue_job("run_triage", job_id)

    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, redis: RedisDep) -> JobResponse:
    """Get job status and details."""
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse.model_validate(json.loads(raw))


# ---------------------------------------------------------------------------
# SSE streaming endpoint
# ---------------------------------------------------------------------------


async def _sse_generator(redis: RedisDep, job_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to Redis Pub/Sub and yield SSE-formatted events."""
    pubsub = redis.pubsub()
    channel = f"jobs:{job_id}:events"
    await pubsub.subscribe(channel)
    seq = 0

    try:
        while True:
            message = await asyncio.wait_for(
                pubsub.get_message(ignore_subscribe_messages=True, timeout=_SSE_KEEPALIVE_SECONDS),
                timeout=_SSE_KEEPALIVE_SECONDS + 5,
            )
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
            if event_type in ("job.done", "job.failed"):
                break
    except TimeoutError:
        yield ":keepalive\n\n"
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


# ---------------------------------------------------------------------------
# Job control endpoints
# ---------------------------------------------------------------------------


async def _load_job_data(redis: RedisDep, job_id: str) -> dict[str, object]:  # noqa: ANN401 — Redis JSON is untyped
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(raw)


@router.post("/{job_id}/answer", response_model=JobActionResponse)
async def answer_job(
    job_id: str,
    body: AnswerRequest,
    redis: RedisDep,
    graph: GraphDep,
    arq: ArqDep,
) -> JobActionResponse:
    """Resume a job waiting for human input by providing an answer."""
    data = await _load_job_data(redis, job_id)

    if not data.get("awaiting_human"):
        raise HTTPException(status_code=409, detail="Job is not awaiting human input")

    # Cancel the timeout task
    await arq.abort_job(f"timeout:{job_id}")

    # Resume graph execution
    config: RunnableConfig = {"configurable": {"thread_id": job_id}}
    await graph.ainvoke(Command(resume=body.answer), config=config)

    data["awaiting_human"] = False
    data["status"] = "running"
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

    return JobActionResponse(status="answer_received", job_id=job_id)


@router.post("/{job_id}/pause", response_model=JobActionResponse)
async def pause_job(
    job_id: str,
    redis: RedisDep,
) -> JobActionResponse:
    """Request a running job to pause at the next supervisor boundary."""
    data = await _load_job_data(redis, job_id)

    data["status"] = "pausing"
    data["paused"] = True
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

    return JobActionResponse(status="pausing", job_id=job_id)


@router.post("/{job_id}/resume", response_model=JobActionResponse)
async def resume_job(
    job_id: str,
    redis: RedisDep,
    graph: GraphDep,
) -> JobActionResponse:
    """Resume a paused job."""
    data = await _load_job_data(redis, job_id)

    config: RunnableConfig = {"configurable": {"thread_id": job_id}}
    await graph.ainvoke(Command(resume="resume"), config=config)

    data["status"] = "running"
    data["paused"] = False
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

    return JobActionResponse(status="resumed", job_id=job_id)


@router.post("/{job_id}/redirect", response_model=JobActionResponse)
async def redirect_job(
    job_id: str,
    body: RedirectRequest,
    redis: RedisDep,
    graph: GraphDep,
) -> JobActionResponse:
    """Inject a redirect instruction into a running or paused job."""
    data = await _load_job_data(redis, job_id)

    existing = data.get("redirect_instructions")
    instructions: list[str] = [*existing] if existing else []  # type: ignore[misc]
    instructions.append(body.instruction)
    data["redirect_instructions"] = instructions

    # If paused, resume with redirect
    if data.get("paused"):
        config: RunnableConfig = {"configurable": {"thread_id": job_id}}
        await graph.ainvoke(
            Command(resume={"type": "redirect", "instruction": body.instruction}),
            config=config,
        )
        data["paused"] = False
        data["status"] = "running"

    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

    return JobActionResponse(status="redirected", job_id=job_id)


@router.delete("/{job_id}", response_model=JobActionResponse)
async def kill_job(
    job_id: str,
    redis: RedisDep,
    arq: ArqDep,
) -> JobActionResponse:
    """Kill a running job."""
    data = await _load_job_data(redis, job_id)

    # Abort the ARQ task
    await arq.abort_job(job_id)

    data["status"] = "killed"
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

    return JobActionResponse(status="killed", job_id=job_id)
