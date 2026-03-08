
import fakeredis
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_job_returns_202(api_client: AsyncClient) -> None:
    response = await api_client.post("/jobs", json={"issue_url": "https://github.com/acme/backend/issues/1"})
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_answer_when_not_waiting_returns_409(
    api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis
) -> None:
    # Create a running job that is NOT waiting for human input
    await fake_redis.hset("job:test-job-1", mapping={
        "job_id": "test-job-1",
        "status": "running",
        "issue_url": "https://github.com/a/b/issues/1",
        "current_node": "investigator",
        "awaiting_human": "false",
        "langsmith_url": "",
        "supervisor_notes": "",
    })

    response = await api_client.post("/jobs/test-job-1/answer", json={"answer": "The error occurs when..."})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_answer_when_waiting_returns_200(
    api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis
) -> None:
    await fake_redis.hset("job:test-job-2", mapping={
        "job_id": "test-job-2",
        "status": "waiting",
        "issue_url": "https://github.com/a/b/issues/2",
        "current_node": "human_input",
        "awaiting_human": "true",
        "langsmith_url": "",
        "supervisor_notes": "",
    })

    response = await api_client.post("/jobs/test-job-2/answer", json={"answer": "The error occurs when..."})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_pause_job(api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis) -> None:
    await fake_redis.hset("job:test-job-3", mapping={
        "job_id": "test-job-3",
        "status": "running",
        "issue_url": "https://github.com/a/b/issues/3",
        "awaiting_human": "false",
        "langsmith_url": "",
        "current_node": "",
        "supervisor_notes": "",
    })

    response = await api_client.post("/jobs/test-job-3/pause")
    assert response.status_code == 200
    assert response.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_job(api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis) -> None:
    await fake_redis.hset("job:test-job-4", mapping={
        "job_id": "test-job-4",
        "status": "paused",
        "issue_url": "https://github.com/a/b/issues/4",
        "awaiting_human": "false",
        "langsmith_url": "",
        "current_node": "",
        "supervisor_notes": "",
    })

    response = await api_client.post("/jobs/test-job-4/resume")
    assert response.status_code == 200
    assert response.json()["status"] == "resumed"


@pytest.mark.asyncio
async def test_kill_job(api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis) -> None:
    await fake_redis.hset("job:test-job-5", mapping={
        "job_id": "test-job-5",
        "status": "running",
        "issue_url": "https://github.com/a/b/issues/5",
        "awaiting_human": "false",
        "langsmith_url": "",
        "current_node": "",
        "supervisor_notes": "",
    })

    response = await api_client.delete("/jobs/test-job-5")
    assert response.status_code == 200
    assert response.json()["status"] == "killed"


@pytest.mark.asyncio
async def test_redirect_job(api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis) -> None:
    await fake_redis.hset("job:test-job-6", mapping={
        "job_id": "test-job-6",
        "status": "running",
        "issue_url": "https://github.com/a/b/issues/6",
        "awaiting_human": "false",
        "langsmith_url": "",
        "current_node": "",
        "supervisor_notes": "",
    })

    response = await api_client.post("/jobs/test-job-6/redirect", json={"instruction": "Focus on the auth module"})
    assert response.status_code == 200
    assert response.json()["status"] == "redirected"
