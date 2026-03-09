import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.arq import get_arq
from agentops.api.deps.graph import get_graph
from agentops.api.deps.redis import get_redis
from agentops.api.main import create_app


@pytest.fixture
def mock_graph():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=None)
    graph.aget_state = AsyncMock(return_value=MagicMock(tasks=[]))
    return graph


@pytest.fixture
def mock_arq():
    arq = MagicMock()
    arq.abort_job = AsyncMock(return_value=None)
    arq.aclose = AsyncMock(return_value=None)
    return arq


@pytest.fixture
async def control_client(settings, fake_redis, mock_graph, mock_arq):
    app = create_app(settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_graph] = lambda: mock_graph
    app.dependency_overrides[get_arq] = lambda: mock_arq
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_answer_409_when_not_awaiting(control_client, fake_redis, make_job):
    await make_job("job-1", awaiting_human=False)
    resp = await control_client.post("/jobs/job-1/answer", json={"answer": "yes"})
    assert resp.status_code == 409


async def test_answer_200_when_awaiting(control_client, fake_redis, mock_graph, mock_arq, make_job):
    await make_job("job-2", status="waiting", awaiting_human=True)
    resp = await control_client.post("/jobs/job-2/answer", json={"answer": "the fix is X"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "answer_received"
    assert body["job_id"] == "job-2"
    # Verify Redis updated
    raw = await fake_redis.get("job:job-2")
    data = json.loads(raw)
    assert data["status"] == "running"
    assert data["awaiting_human"] is False
    # Verify graph resumed
    mock_graph.ainvoke.assert_called_once()
    mock_arq.abort_job.assert_called_once()


async def test_pause_sets_flag(control_client, fake_redis, make_job):
    await make_job("job-3", status="running")
    resp = await control_client.post("/jobs/job-3/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pausing"
    raw = await fake_redis.get("job:job-3")
    data = json.loads(raw)
    assert data["paused"] is True
    assert data["status"] == "pausing"


async def test_resume_clears_flag(control_client, fake_redis, mock_graph, make_job):
    await make_job("job-4", status="paused", paused=True)
    resp = await control_client.post("/jobs/job-4/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resumed"
    raw = await fake_redis.get("job:job-4")
    data = json.loads(raw)
    assert data["paused"] is False
    assert data["status"] == "running"
    mock_graph.ainvoke.assert_called_once()


async def test_kill_sets_status(control_client, fake_redis, mock_arq, make_job):
    await make_job("job-5", status="running")
    resp = await control_client.delete("/jobs/job-5")
    assert resp.status_code == 200
    assert resp.json()["status"] == "killed"
    raw = await fake_redis.get("job:job-5")
    data = json.loads(raw)
    assert data["status"] == "killed"
    mock_arq.abort_job.assert_called_once_with("job-5")


async def test_redirect_stores_instruction(control_client, fake_redis, make_job):
    await make_job("job-6", status="running")
    resp = await control_client.post(
        "/jobs/job-6/redirect", json={"instruction": "focus on auth module"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "redirected"
    raw = await fake_redis.get("job:job-6")
    data = json.loads(raw)
    assert "focus on auth module" in data["redirect_instructions"]


async def test_redirect_resumes_paused_job(control_client, fake_redis, mock_graph, make_job):
    await make_job("job-7", status="paused", paused=True)
    resp = await control_client.post(
        "/jobs/job-7/redirect", json={"instruction": "look at DB layer"}
    )
    assert resp.status_code == 200
    raw = await fake_redis.get("job:job-7")
    data = json.loads(raw)
    assert data["paused"] is False
    assert data["status"] == "running"
    mock_graph.ainvoke.assert_called_once()


async def test_answer_404_missing_job(control_client):
    resp = await control_client.post("/jobs/nonexistent/answer", json={"answer": "yes"})
    assert resp.status_code == 404


async def test_get_job_includes_new_fields(control_client, fake_redis, make_job):
    await make_job("job-8", awaiting_human=True, current_node="human_input")
    resp = await control_client.get("/jobs/job-8")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awaiting_human"] is True
    assert body["current_node"] == "human_input"
