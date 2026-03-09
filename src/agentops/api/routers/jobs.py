import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agentops.api.deps.redis import RedisDep

router = APIRouter(prefix="/jobs", tags=["jobs"])

_GITHUB_ISSUE_URL_PATTERN = r"^https://github\.com/[^/]+/[^/]+/issues/\d+$"

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
    langsmith_url: str = ""


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CreateJobResponse)
async def create_job(
    body: CreateJobRequest,
    redis: RedisDep,
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
    }
    await redis.setex(f"job:{job_id}", 86400, json.dumps(job_data))

    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, redis: RedisDep) -> JobResponse:
    """Get job status and details."""
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse.model_validate(json.loads(raw))
