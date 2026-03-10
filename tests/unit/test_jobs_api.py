from unittest.mock import MagicMock

from httpx import AsyncClient


async def test_create_job_returns_200(api_client: AsyncClient, mock_arq: MagicMock) -> None:
    resp = await api_client.post(
        "/graphql",
        json={
            "query": """
                mutation($input: CreateJobInput!) {
                    createJob(input: $input) { jobId status }
                }
            """,
            "variables": {"input": {"issueUrl": "https://github.com/acme/backend/issues/1"}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["createJob"]
    assert "jobId" in data
    assert data["status"] == "queued"
    mock_arq.enqueue_job.assert_called_once_with("run_triage", data["jobId"], _job_id=data["jobId"])


async def test_create_job_invalid_url_returns_error(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/graphql",
        json={
            "query": """
                mutation($input: CreateJobInput!) {
                    createJob(input: $input) { jobId status }
                }
            """,
            "variables": {"input": {"issueUrl": "https://not-github.com/x"}},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("errors") is not None


async def test_create_job_idempotency(api_client: AsyncClient, mock_arq: MagicMock) -> None:
    query = """
        mutation($input: CreateJobInput!) {
            createJob(input: $input) { jobId status }
        }
    """
    variables = {"input": {"issueUrl": "https://github.com/acme/backend/issues/99"}}
    r1 = await api_client.post("/graphql", json={"query": query, "variables": variables})
    r2 = await api_client.post("/graphql", json={"query": query, "variables": variables})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["data"]["createJob"]["jobId"] == r2.json()["data"]["createJob"]["jobId"]
    mock_arq.enqueue_job.assert_called_once()


async def test_get_job_not_found(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/graphql",
        json={
            "query": '{ job(jobId: "nonexistent-id") { jobId status } }',
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("errors") is not None


async def test_get_job_found(api_client: AsyncClient) -> None:
    create_resp = await api_client.post(
        "/graphql",
        json={
            "query": """
                mutation($input: CreateJobInput!) {
                    createJob(input: $input) { jobId status }
                }
            """,
            "variables": {"input": {"issueUrl": "https://github.com/acme/backend/issues/5"}},
        },
    )
    job_id = create_resp.json()["data"]["createJob"]["jobId"]
    get_resp = await api_client.post(
        "/graphql",
        json={
            "query": "query($id: ID!) { job(jobId: $id) { jobId issueUrl status } }",
            "variables": {"id": job_id},
        },
    )
    data = get_resp.json()["data"]["job"]
    assert data["jobId"] == job_id
    assert data["issueUrl"] == "https://github.com/acme/backend/issues/5"


async def test_health_check(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
