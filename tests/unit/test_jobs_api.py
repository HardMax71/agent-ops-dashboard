from httpx import AsyncClient


async def test_create_job_returns_202(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/jobs", json={"issue_url": "https://github.com/acme/backend/issues/1"}
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"


async def test_create_job_invalid_url_returns_422(api_client: AsyncClient) -> None:
    response = await api_client.post("/jobs", json={"issue_url": "https://not-github.com/x"})
    assert response.status_code == 422


async def test_create_job_idempotency(api_client: AsyncClient) -> None:
    payload = {"issue_url": "https://github.com/acme/backend/issues/99"}
    r1 = await api_client.post("/jobs", json=payload)
    r2 = await api_client.post("/jobs", json=payload)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["job_id"] == r2.json()["job_id"]


async def test_get_job_not_found(api_client: AsyncClient) -> None:
    response = await api_client.get("/jobs/nonexistent-id")
    assert response.status_code == 404


async def test_get_job_found(api_client: AsyncClient) -> None:
    create_resp = await api_client.post(
        "/jobs", json={"issue_url": "https://github.com/acme/backend/issues/5"}
    )
    job_id = create_resp.json()["job_id"]
    get_resp = await api_client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["job_id"] == job_id
    assert data["issue_url"] == "https://github.com/acme/backend/issues/5"


async def test_health_check(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
