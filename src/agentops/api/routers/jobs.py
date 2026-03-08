import hashlib
import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agentops.api.deps.redis import RedisDep
from agentops.api.deps.settings import SettingsDep

router = APIRouter(prefix="/jobs", tags=["jobs"])

_GITHUB_ISSUE_URL_PATTERN = r"^https://github\.com/[^/]+/[^/]+/issues/\d+$"


class CreateJobRequest(BaseModel):
    issue_url: str
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


class FeedbackRequest(BaseModel):
    key: str
    score: float
    comment: str = ""


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CreateJobResponse)
async def create_job(
    body: CreateJobRequest,
    redis: RedisDep,
    settings: SettingsDep,
) -> CreateJobResponse:
    """Create a new triage job. Idempotent within 24h per issue URL."""
    import re
    if not re.match(_GITHUB_ISSUE_URL_PATTERN, body.issue_url):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid GitHub issue URL")

    owner_id = "anonymous"
    idempotency_key = f"idempotency:{hashlib.sha256(body.issue_url.encode()).hexdigest()}"
    existing_job_id = await redis.get(idempotency_key)
    if existing_job_id is not None:
        return CreateJobResponse(job_id=existing_job_id, status="queued")

    job_id = str(uuid.uuid4())
    job_data = {
        "job_id": job_id,
        "status": "queued",
        "issue_url": body.issue_url,
        "supervisor_notes": body.supervisor_notes,
        "owner_id": owner_id,
        "langsmith_url": "",
        "awaiting_human": "false",
        "current_node": "",
    }
    await redis.hset(f"job:{job_id}", mapping=job_data)
    await redis.expire(f"job:{job_id}", 86400)
    await redis.setex(idempotency_key, 86400, job_id)

    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, redis: RedisDep) -> JobResponse:
    """Get job status and details."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return JobResponse(
        job_id=data.get("job_id", job_id),
        status=data.get("status", "queued"),
        issue_url=data.get("issue_url", ""),
        langsmith_url=data.get("langsmith_url", ""),
        awaiting_human=data.get("awaiting_human", "false") == "true",
        current_node=data.get("current_node", ""),
    )


@router.post("/{job_id}/answer", response_model=dict)
async def answer_job(job_id: str, body: AnswerRequest, redis: RedisDep) -> dict[str, str]:
    """Submit human answer to resume a waiting job."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if data.get("awaiting_human", "false") != "true":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job is not waiting for human input")

    await redis.setex(f"job:{job_id}:answer", 3600, body.answer)
    await redis.hset(f"job:{job_id}", mapping={"status": "running", "awaiting_human": "false"})
    await redis.expire(f"job:{job_id}", 86400)

    return {"status": "answer_received"}


@router.post("/{job_id}/pause", response_model=dict)
async def pause_job(job_id: str, redis: RedisDep) -> dict[str, str]:
    """Pause a running job."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    await redis.hset(f"job:{job_id}", mapping={"status": "paused"})
    await redis.expire(f"job:{job_id}", 86400)
    return {"status": "paused"}


@router.post("/{job_id}/resume", response_model=dict)
async def resume_job(job_id: str, redis: RedisDep) -> dict[str, str]:
    """Resume a paused job."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    await redis.hset(f"job:{job_id}", mapping={"status": "running", "paused": "false"})
    await redis.expire(f"job:{job_id}", 86400)
    return {"status": "resumed"}


@router.post("/{job_id}/redirect", response_model=dict)
async def redirect_job(job_id: str, body: RedirectRequest, redis: RedisDep) -> dict[str, str]:
    """Redirect a job with a new instruction."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    await redis.hset(f"job:{job_id}", mapping={"supervisor_notes": body.instruction})
    await redis.expire(f"job:{job_id}", 86400)
    return {"status": "redirected"}


@router.delete("/{job_id}", response_model=dict)
async def kill_job(job_id: str, redis: RedisDep) -> dict[str, str]:
    """Kill a job."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    await redis.hset(f"job:{job_id}", mapping={"status": "killed"})
    await redis.expire(f"job:{job_id}", 86400)
    await redis.delete(f"job:{job_id}:answer")
    return {"status": "killed"}


@router.get("/{job_id}/stream")
async def stream_job(job_id: str, redis: RedisDep) -> StreamingResponse:
    """Stream job events via SSE."""
    channel = f"jobs:{job_id}:events"

    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        seq = 0
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            yield f"id: {seq}\ndata: {message['data']}\n\n"
            seq += 1
            if json.loads(message["data"]).get("type") == "job.done":
                break
        await pubsub.unsubscribe(channel)
        await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{job_id}/post-comment")
async def post_github_comment(job_id: str, redis: RedisDep) -> dict[str, str]:
    """Post triage report as GitHub comment. Full implementation uses DB token."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {"status": "comment_posted", "job_id": job_id}


@router.post("/{job_id}/create-ticket")
async def create_github_ticket(job_id: str, redis: RedisDep) -> dict[str, str]:
    """Create GitHub issue from ticket draft. Full implementation uses DB token."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {"status": "ticket_created", "job_id": job_id}


@router.post("/{job_id}/feedback")
async def submit_job_feedback(
    job_id: str,
    body: FeedbackRequest,
    redis: RedisDep,
    settings: SettingsDep,
) -> dict[str, str]:
    """Submit LangSmith feedback for a job."""
    data = await redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    run_id = data.get("langsmith_run_id", "")
    if run_id and settings.langsmith_api_key:
        from agentops.langsmith_handler import LangSmithFeedbackHandler
        handler = LangSmithFeedbackHandler(
            api_key=settings.langsmith_api_key,
            org_id=settings.langsmith_org_id,
            project_id=settings.langsmith_project_id,
        )
        await handler.submit_feedback(run_id, body.key, body.score, body.comment)
    return {"status": "feedback_submitted", "job_id": job_id}
