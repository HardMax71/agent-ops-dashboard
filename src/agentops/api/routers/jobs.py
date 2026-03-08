import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agentops.api.deps.redis import RedisDep
from agentops.api.deps.settings import SettingsDep

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
    settings: SettingsDep,
) -> CreateJobResponse:
    """Create a new triage job. Idempotent within 24h per issue URL."""
    # Idempotency key (owner_id placeholder until auth is implemented)
    owner_id = "anonymous"
    idempotency_key = (
        f"idempotency:{hashlib.sha256(f'{body.issue_url}{owner_id}'.encode()).hexdigest()}"
    )

    existing_job_id = await redis.get(idempotency_key)
    if existing_job_id is not None:
        return CreateJobResponse(job_id=existing_job_id, status="queued")

    job_id = str(uuid.uuid4())
    job_data = {
        "job_id": job_id,
        "status": "queued",
        "issue_url": body.issue_url,
        "supervisor_notes": body.supervisor_notes,
        "langsmith_url": "",
    }
    await redis.setex(f"job:{job_id}", 86400, json.dumps(job_data))
    await redis.setex(idempotency_key, 86400, job_id)

    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, redis: RedisDep) -> JobResponse:
    """Get job status and details."""
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")

    data = json.loads(raw)
    return JobResponse(
        job_id=data["job_id"],
        status=data["status"],
        issue_url=data["issue_url"],
        langsmith_url=data.get("langsmith_url", ""),
    )
