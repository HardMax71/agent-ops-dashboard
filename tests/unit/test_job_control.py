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
async def control_client(settings, fake_redis, mock_graph, mock_arq):
    app = create_app(settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_graph] = lambda: mock_graph
    app.dependency_overrides[get_arq] = lambda: mock_arq
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_answer_error_when_not_awaiting(control_client, fake_redis, make_job):
    await make_job("job-1", awaiting_human=False)
    resp = await control_client.post(
        "/graphql",
        json={
            "query": 'mutation { answerJob(jobId: "job-1", answer: "yes") { status jobId } }',
        },
    )
    body = resp.json()
    errors = body["errors"]
    assert any("not awaiting human input" in e["message"] for e in errors)


async def test_answer_when_awaiting(control_client, fake_redis, mock_graph, mock_arq, make_job):
    await make_job("job-2", status="waiting", awaiting_human=True)
    resp = await control_client.post(
        "/graphql",
        json={
            "query": (
                'mutation { answerJob(jobId: "job-2", answer: "the fix is X") { status jobId } }'
            ),
        },
    )
    data = resp.json()["data"]["answerJob"]
    assert data["status"] == "answer_received"
    assert data["jobId"] == "job-2"
    raw = await fake_redis.get("job:job-2")
    job_data = json.loads(raw)
    assert job_data["status"] == "running"
    assert job_data["awaiting_human"] is False
    # abort is now done via Redis zadd, not arq.abort_job
    abort_score = await fake_redis.zscore("arq:abort", "timeout:job-2")
    assert abort_score is not None
    mock_arq.enqueue_job.assert_called_once_with(
        "resume_graph", "job-2", "the fix is X", _job_id="job-2"
    )


async def test_pause_sets_flag(control_client, fake_redis, make_job):
    await make_job("job-3", status="running")
    resp = await control_client.post(
        "/graphql",
        json={
            "query": 'mutation { pauseJob(jobId: "job-3") { status jobId } }',
        },
    )
    data = resp.json()["data"]["pauseJob"]
    assert data["status"] == "pausing"
    raw = await fake_redis.get("job:job-3")
    job_data = json.loads(raw)
    assert job_data["paused"] is True
    assert job_data["status"] == "pausing"


async def test_resume_clears_flag(control_client, fake_redis, mock_arq, make_job):
    await make_job("job-4", status="paused", paused=True)
    resp = await control_client.post(
        "/graphql",
        json={
            "query": 'mutation { resumeJob(jobId: "job-4") { status jobId } }',
        },
    )
    data = resp.json()["data"]["resumeJob"]
    assert data["status"] == "resumed"
    raw = await fake_redis.get("job:job-4")
    job_data = json.loads(raw)
    assert job_data["paused"] is False
    assert job_data["status"] == "running"
    mock_arq.enqueue_job.assert_called_once_with("resume_graph", "job-4", "resume", _job_id="job-4")


async def test_kill_sets_status(control_client, fake_redis, mock_arq, make_job):
    await make_job("job-5", status="running")
    resp = await control_client.post(
        "/graphql",
        json={
            "query": 'mutation { killJob(jobId: "job-5") { status jobId } }',
        },
    )
    data = resp.json()["data"]["killJob"]
    assert data["status"] == "killed"
    raw = await fake_redis.get("job:job-5")
    job_data = json.loads(raw)
    assert job_data["status"] == "killed"
    abort_score = await fake_redis.zscore("arq:abort", "job-5")
    assert abort_score is not None


async def test_redirect_stores_instruction(control_client, fake_redis, make_job):
    await make_job("job-6", status="running")
    resp = await control_client.post(
        "/graphql",
        json={
            "query": (
                'mutation { redirectJob(jobId: "job-6",'
                ' instruction: "focus on auth module") { status jobId } }'
            ),
        },
    )
    data = resp.json()["data"]["redirectJob"]
    assert data["status"] == "redirected"
    raw = await fake_redis.get("job:job-6")
    job_data = json.loads(raw)
    assert "focus on auth module" in job_data["redirect_instructions"]


async def test_redirect_resumes_paused_job(control_client, fake_redis, mock_arq, make_job):
    await make_job("job-7", status="paused", paused=True)
    resp = await control_client.post(
        "/graphql",
        json={
            "query": (
                'mutation { redirectJob(jobId: "job-7",'
                ' instruction: "look at DB layer") { status jobId } }'
            ),
        },
    )
    assert resp.json()["data"]["redirectJob"]["status"] == "redirected"
    raw = await fake_redis.get("job:job-7")
    job_data = json.loads(raw)
    assert job_data["paused"] is False
    assert job_data["status"] == "running"
    mock_arq.enqueue_job.assert_called_once_with(
        "resume_graph",
        "job-7",
        json.dumps({"type": "redirect", "instruction": "look at DB layer"}),
        True,
        _job_id="job-7",
    )


async def test_answer_error_missing_job(control_client):
    resp = await control_client.post(
        "/graphql",
        json={
            "query": 'mutation { answerJob(jobId: "nonexistent", answer: "yes") { status jobId } }',
        },
    )
    assert resp.json().get("errors") is not None


async def test_get_job_includes_new_fields(control_client, fake_redis, make_job):
    await make_job("job-8", awaiting_human=True, current_node="human_input")
    resp = await control_client.post(
        "/graphql",
        json={
            "query": '{ job(jobId: "job-8") { jobId awaitingHuman currentNode } }',
        },
    )
    data = resp.json()["data"]["job"]
    assert data["awaitingHuman"] is True
    assert data["currentNode"] == "human_input"
