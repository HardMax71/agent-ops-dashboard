import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field

from agentops.api.deps.arq import ArqDep
from agentops.api.deps.graph import GraphDep
from agentops.api.deps.redis import RedisDep

router = APIRouter(prefix="/jobs", tags=["jobs"])

_GITHUB_ISSUE_URL_PATTERN = r"^https://github\.com/[^/]+/[^/]+/issues/\d+$"

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
) -> CreateJobResponse:
    """Create a new triage job. Idempotent within 24h per issue URL."""
    # Idempotency key (owner_id placeholder until auth is implemented)
    owner_id = "anonymous"
    idempotency_key = (
        f"idempotency:{hashlib.sha256(f'{body.issue_url}{owner_id}'.encode()).hexdigest()}"
    )

    job_id = str(uuid.uuid4())
    set_result = await redis.set(idempotency_key, job_id, nx=True, ex=86400)
    if set_result is None:
        existing_job_id = await redis.get(idempotency_key)
        return CreateJobResponse(job_id=existing_job_id or job_id, status="queued")

    job_data = {
        "job_id": job_id,
        "status": "queued",
        "issue_url": body.issue_url,
        "supervisor_notes": body.supervisor_notes,
        "langsmith_url": "",
        "awaiting_human": False,
        "current_node": "",
    }
    await redis.setex(f"job:{job_id}", 86400, json.dumps(job_data))
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
