---
id: PRD-013
title: Testing Strategy & CI
status: DRAFT
domain: tooling/testing
depends_on: [ PRD-003, PRD-004, PRD-006, PRD-007, PRD-008, PRD-011, PRD-012 ]
---

# PRD-013 — Testing Strategy & CI

## §1 Purpose & Scope

This PRD establishes the complete testing strategy for the Agent Ops Dashboard: what to test, at what layer, which
libraries to use, and how CI executes each layer.

**Three test layers:**

- **Unit** — mocked dependencies, no I/O, fast (< 100 ms per test)
- **Integration** — real Redis and Postgres via testcontainers, real HTTP via ASGI transport
- **E2E** — Playwright browser tests against a running dev server

**Out of scope:** LLM evaluation (PRD-010) — that uses LangSmith with a different cadence and toolchain.

**CI coverage:** All layers run in CI. E2E runs on merge to `main` only; unit and integration run on every push and PR.

---

## §2 Test Directory Layout

```
tests/
├── conftest.py                       # global fixtures: fake_redis, fake_llm, async_client, NoOpMeterProvider
├── fixtures/
│   └── issues/                       # JSON fixture files for parametrized chain tests
│       ├── issue_001.json
│       ├── issue_002.json
│       └── issue_003.json
├── unit/
│   ├── test_data_validation.py       # GitHubIssueUrl parametrize (valid/invalid URLs)
│   ├── test_investigator_chain.py    # FakeListChatModel, assert prompt structure
│   ├── test_web_search_agent.py      # ToolNode, mock Tavily tool
│   ├── test_critic_chain.py          # CriticVerdict binary verdict
│   ├── test_writer_chain.py          # RunnableParallel merge
│   ├── test_supervisor_node.py       # SupervisorDecision routing guards
│   ├── test_transform_event.py       # transform_langgraph_event() per event type
│   ├── test_auth_tokens.py           # JWT encode/decode, Fernet encryption
│   ├── test_metrics_callback.py      # AgentOpsMetricsCallback with InMemoryMetricReader
│   └── test_event_bus.py             # EventBus subscribe/publish/error isolation
├── integration/
│   ├── conftest.py                   # session-scoped containers (RedisContainer, PostgresContainer)
│   ├── test_api_jobs.py              # POST /jobs idempotency, GET /jobs/{id}, 422 on bad URL
│   ├── test_api_auth.py              # OAuth callback, refresh token, cookie flags, 401 paths
│   ├── test_api_stream.py            # SSE endpoint, ≥5 events emitted, disconnect cleanup
│   ├── test_graph_lifecycle.py       # graph.ainvoke with MemorySaver, state transitions, interrupt
│   ├── test_arq_worker.py            # run_triage task, job.done / job.failed SSE events
│   └── test_job_control.py           # pause, resume, redirect, kill, answer endpoints
└── e2e/
    ├── conftest.py                   # Playwright fixtures, dev server
    └── test_full_job_flow.py         # submit → stream → output panel
```

---

## §3 Core Dependencies

Add to `pyproject.toml` under `[dependency-groups]`:

```toml
[dependency-groups]
test = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-xdist>=3.6",
    "pytest-cov>=5.0",
    "fakeredis[aioredis]>=2.26",
    "testcontainers[redis,postgres]>=4.8",
    "httpx>=0.27",
    "asgi-lifespan>=2.1",
    "langchain-tests>=0.3",
    "playwright>=1.44",
    "pytest-timeout>=2.1",
]
```

**No `anyio` separately** — `pytest-asyncio` pulls it.
**No `aioredis` separately** — `fakeredis[aioredis]` pulls it.

---

## §4 `pyproject.toml` Test Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
addopts = [
    "-ra",
    "--strict-markers",
    "--cov=src",
    "--cov-branch",
    "--cov-report=term-missing:skip-covered",
    "--cov-report=xml:coverage.xml",
    "--cov-fail-under=80",
]
markers = [
    "integration: requires live Redis and Postgres containers",
    "e2e: requires Playwright and running dev server",
    "slow: takes more than 2 seconds",
]

[tool.coverage.run]
branch = true
source = ["src"]
omit = ["src/**/migrations/*", "src/**/__main__.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "@overload",
]
precision = 2
```

xdist flags (`-n auto --dist worksteal`) are **not** in `addopts` — a bare `pytest` invocation is single-process,
which is correct for integration and E2E runs. Parallelism is opt-in: the CI unit job passes `-n auto --dist worksteal`
explicitly on the command line (see §8). Integration tests are gated by `pytest -m integration`; containers are
session-scoped and cannot be shared across workers.

---

## §5 Global `conftest.py` Fixtures

Six fixtures live at `tests/conftest.py`:

| Fixture                    | Scope      | Returns                                             | Implementation                                         |
|----------------------------|------------|-----------------------------------------------------|--------------------------------------------------------|
| `fake_redis`               | `function` | `FakeAsyncRedis(decode_responses=True)`             | `fakeredis.FakeAsyncRedis`                             |
| `fake_llm`                 | `function` | `FakeListChatModel(responses=[...])`                | `langchain_core.language_models.fake_chat_models`      |
| `memory_checkpointer`      | `function` | `MemorySaver()`                                     | `langgraph.checkpoint.memory`                          |
| `async_client`             | `function` | `AsyncClient` + `ASGITransport` + `LifespanManager` | `httpx` + `asgi_lifespan`                              |
| `override_auth`            | `function` | sets `app.dependency_overrides[get_current_user]`   | cleared in teardown                                    |
| `noop_metrics`             | `function` | —                                                   | patches OTel internals via `monkeypatch`; opt-in per test |

`noop_metrics` is function-scoped and **not** `autouse` — tests that need OTel silenced request it explicitly.

**Why `set_meter_provider()` cannot be used for test isolation:** The Python OTel SDK guards
`set_meter_provider()` with `_METER_PROVIDER_SET_ONCE = Once()`. `Once.do_once()` executes its
argument exactly once per process lifetime; every subsequent call is a silent no-op (plus a
`WARNING: Overriding of current MeterProvider is not allowed` log). Calling
`set_meter_provider(NoOpMeterProvider())` a second time in the same worker process does nothing —
the first provider installed remains active for the rest of the process.

**Correct isolation pattern:** Patch the two internal globals directly with `monkeypatch` so
pytest restores them automatically after each test:

```python
import opentelemetry.metrics._internal as _otel_metrics
from opentelemetry.util._once import Once

@pytest.fixture()
def noop_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_otel_metrics, "_METER_PROVIDER", NoOpMeterProvider())
    monkeypatch.setattr(_otel_metrics, "_METER_PROVIDER_SET_ONCE", Once())
```

`test_metrics_callback.py` uses the same pattern, substituting `NoOpMeterProvider()` with
`MeterProvider(reader=InMemoryMetricReader())`, so each test gets a fresh provider with an empty
reader. After the test, `monkeypatch` resets the globals to whatever they were before the test.

```python
# tests/conftest.py (sketch)

import pytest
from agentops.api.deps import get_current_user
from agentops.api.main import app
from agentops.api.models import CurrentUser
from asgi_lifespan import LifespanManager
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import MemorySaver
import opentelemetry.metrics._internal as _otel_metrics
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.util._once import Once


@pytest.fixture()
async def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture()
def fake_llm() -> FakeListChatModel:
    return FakeListChatModel(responses=[])


@pytest.fixture()
def memory_checkpointer() -> MemorySaver:
    return MemorySaver()


@pytest.fixture()
async def async_client() -> AsyncClient:
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as client:
            yield client


@pytest.fixture()
def fake_user() -> CurrentUser:
    return CurrentUser(id="test-user-id", github_login="testuser", github_id=1234567)


@pytest.fixture()
def override_auth(fake_user) -> None:
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def noop_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    # set_meter_provider() is set-once (Once guard) — patch internals directly
    # so monkeypatch restores original state after each test.
    monkeypatch.setattr(_otel_metrics, "_METER_PROVIDER", NoOpMeterProvider())
    monkeypatch.setattr(_otel_metrics, "_METER_PROVIDER_SET_ONCE", Once())
```

---

## §6 Unit Test Specs

### 6.1 Data Validation (`test_data_validation.py`)

- `@pytest.mark.parametrize` with a table of `(url, expected_status)` covering:
    - **6 valid cases:** standard HTTPS, numeric owner, dash in repo name, underscore in repo name, high issue number (7
      digits), `.git`-less URL
    - **8 invalid cases:** `http://` scheme, wrong host, local file path, missing issue segment, non-numeric ID,
      trailing slash with no ID, query params appended, encoded path traversal
- Test idempotency key: `SHA-256(url + ":" + owner_id)` is deterministic and unique across users (same URL + different
  owner_id → different key)

```python
@pytest.mark.parametrize("url,expected_status", [
    ("https://github.com/owner/repo/issues/1", 202),
    ("https://github.com/owner123/repo/issues/99999", 202),
    ("https://github.com/my-org/repo-name/issues/42", 202),
    ("http://github.com/owner/repo/issues/1", 422),
    ("https://gitlab.com/owner/repo/issues/1", 422),
    ("https://github.com/owner/repo/issues/abc", 422),
    ("https://github.com/owner/repo/issues/", 422),
    ("https://github.com/owner/repo/issues/1?foo=bar", 422),
], ids=["valid-std", "valid-numeric", "valid-dashes", "invalid-http",
        "invalid-host", "invalid-id-str", "invalid-trailing-slash", "invalid-query"])
def test_github_url_validation(url: str, expected_status: int) -> None: ...
```

### 6.2 LCEL Agent Chains (5 agents)

**Pattern for all chain tests:**

1. Inject `FakeListChatModel` with predefined JSON responses matching the output schema
2. Assert output is a valid Pydantic model instance — structural assertion on typed attributes, not `isinstance()`
3. Assert fallback chain is invoked when primary raises `RateLimitError` (monkeypatch `primary_chain.invoke`)
4. Assert retry fires exactly 3× before fallback activates (use a counter mock)

**Per-agent additions:**

- **Investigator (`test_investigator_chain.py`):** parametrize with 3 issue fixture files from
  `tests/fixtures/issues/*.json`
- **Web Search (`test_web_search_agent.py`):** mock `_tool_node.ainvoke` to return synthetic `ToolMessage`; assert
  `on_tool_start` fires via event capture on a real graph with `MemorySaver`
- **Critic (`test_critic_chain.py`):** parametrize `verdict` over `["APPROVED", "REJECTED"]`; assert `required_evidence`
  is empty when `APPROVED`. Additionally, test `map_critique_to_verdict` directly with all input combinations:

  | `CritiqueFinding.verdict` | `ready_for_report` | Expected `CriticVerdict.verdict` |
  |---|---|---|
  | `"CONFIRMED"` | `True` | `"APPROVED"` |
  | `"CONFIRMED"` | `False` | `"REJECTED"` |
  | `"UNCERTAIN"` | `False` | `"REJECTED"` |
  | `"CHALLENGED"` | `False` | `"REJECTED"` |

  For each case: assert `result.verdict == expected`; when expected is `"APPROVED"` assert both `result.gaps`
  and `result.required_evidence` are empty; when `"REJECTED"` assert `result.gaps` is non-empty.
- **Writer (`test_writer_chain.py`):** assert `merge_writer_outputs` produces `WriterOutput` with all fields populated;
  test `ticket.get("effort", "M")` default value

### 6.3 Supervisor Node (`test_supervisor_node.py`)

- Test all 5 routing guards in `route_from_supervisor()` as a pure function — no LLM needed:
  - Guard 1: `iterations == 0` forces `"investigator"` regardless of LLM decision
  - Guard 2: `len(human_exchanges) >= 2` blocks `"human_input"`, redirects to `"codebase_search"`
  - Guard 3: `iterations >= max_iterations` forces `"writer"` regardless of verdict
  - Guard 4: `decision == "end"` with no report forces `"writer"`
  - Guard 5: `critic_feedback.verdict == "REJECTED"` blocks `"writer"`, redirects to `"investigator"`
- Test `_invoke_supervisor` retry: first call raises `ValidationError`, second succeeds → returns decision
- Test `_invoke_supervisor` double failure → returns `_FORCED_FALLBACK`
- Test `temperature=0` is set on `_supervisor_llm` (read attribute directly — verifies spec compliance without mocking)

### 6.4 Event Transform (`test_transform_event.py`)

- Parametrize over all 7 `astream_events` event types from PRD-003-1 §3 table
- For each: assert output SSE event type, `agent_id` tracking in `spawned_agents`, drop conditions
- Test `_extract_token` with both OpenAI (`str`) and Anthropic (`list`) token formats
- Test `_section_from_ns` parses checkpoint namespace with `|` separator correctly

### 6.5 Auth Tokens (`test_auth_tokens.py`)

- JWT encode → decode roundtrip with `leeway=timedelta(seconds=30)`
- Expired token raises 401 (advance clock by 16 min using `freezegun`)
- `secure` cookie flag: `True` for staging/production environments, `False` for development
- Fernet encrypt → decrypt roundtrip for GitHub OAuth token
- Refresh token Redis value format: `"{github_id}:{github_login}"` — colon-separated, plain string, NOT JSON

### 6.6 Metrics Callback (`test_metrics_callback.py`)

- Use `InMemoryMetricReader` (not `NoOpMeterProvider`) — this module does not use the function-scoped opt-in `noop_metrics` fixture (see §5); it installs its own `MeterProvider(reader=InMemoryMetricReader())` at each test start
- Assert `on_chain_start` increments `agent_calls_total` counter by exactly 1
- Assert `on_chain_end` records a positive value in `agent_duration_seconds` histogram
- Assert `on_chain_error` increments `agent_errors_total`
- Assert LangGraph nodes NOT in `WORKER_NODES` produce zero metric increments

---

## §7 Integration Test Specs

### Integration `conftest.py`

Session-scoped containers; each test gets a function-scoped connection:

```python
# tests/integration/conftest.py

import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer() as c:
        yield c


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as c:
        yield c
```

**Redis isolation:** tests use namespaced keys `test_{worker_id}_{uuid}:*` and flush only their namespace in teardown.
**DB isolation:** each test runs inside a transaction that rolls back on teardown — no persistent state between tests.

### 7.1 API Jobs (`test_api_jobs.py`)

| Scenario                                 | Expected                             |
|------------------------------------------|--------------------------------------|
| `POST /jobs` with valid URL              | 202 + job_id (UUID)                  |
| Same URL + same user within TTL          | 200 + same job_id (idempotency)      |
| Same URL + different user                | 202 + new job_id                     |
| `POST /jobs` with invalid URL (×4 types) | 422                                  |
| `GET /jobs/{id}`                         | job metadata matches creation params |
| `GET /jobs/{nonexistent}`                | 404                                  |

### 7.2 Auth Flow (`test_api_auth.py`)

| Scenario                                         | Expected                                 |
|--------------------------------------------------|------------------------------------------|
| OAuth callback with valid code                   | sets access token + refresh cookie → 200 |
| OAuth callback with mismatched state             | 400                                      |
| `POST /auth/refresh` with valid cookie           | new access token, extended cookie TTL    |
| `POST /auth/refresh` with expired/missing cookie | 401                                      |
| `GET /auth/me` with valid token                  | returns `github_id`, `github_login`      |
| `GET /auth/me` with expired token                | 401                                      |

### 7.3 SSE Stream (`test_api_stream.py`)

- Stream a completed job (pre-seeded in Redis) → assert `job.done` event received
- Stream ≥5 events before completion
- Disconnect mid-stream → assert `pubsub.unsubscribe()` called (no goroutine/task leak)
- Stream non-existent job → 404

### 7.4 Graph Lifecycle (`test_graph_lifecycle.py`)

- `graph.ainvoke` with `MemorySaver` + fake supervisor → assert state snapshot after each node
- Interrupt at `human_input` → assert `state.awaiting_human == True`
- Resume with `Command(resume="answer")` → assert `human_exchanges` has 1 completed entry with the answer
- `max_iterations` guard fires when `iterations >= max_iterations` → routes to writer node

### 7.5 ARQ Worker (`test_arq_worker.py`)

- Execute `run_triage` in-process using `MemorySaver` graph + fake LLM
- Assert `job.done` SSE event is published to the Redis channel after successful graph completion
- Assert `job.failed` SSE event is published when graph raises (inject error via monkeypatch)

---

## §8 CI — GitHub Actions

### `.github/workflows/ci.yml` — every push and PR

```yaml
name: CI
on:
  push:
    branches: [ main, "feat/**" ]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group test
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run ty check src/

  unit:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group test
      - run: |
          uv run pytest tests/unit/ \
            -n auto --dist worksteal \
            --cov=src --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4
        with:
          files: coverage.xml

  integration:
    runs-on: ubuntu-latest
    needs: unit
    # No services block — RedisContainer and PostgresContainer fixtures spin up
    # their own containers via testcontainers; REDIS_URL / DATABASE_URL are not
    # needed as env vars because the fixtures inject connection details directly.
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group test
      - run: |
          uv run pytest tests/integration/ -m integration \
            --cov=src --cov-append --cov-report=xml
        env:
          OPENAI_API_KEY: sk-fake-for-ci
          GITHUB_OAUTH_CLIENT_ID: fake
          GITHUB_OAUTH_CLIENT_SECRET: fake
          JWT_SECRET: fake-secret-for-ci
          GITHUB_TOKEN_ENCRYPTION_KEY: ${{ secrets.GITHUB_TOKEN_ENCRYPTION_KEY_TEST }}
      - uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
          flags: integration
```

### `.github/workflows/e2e.yml` — merge to `main` only

```yaml
name: E2E
on:
  push:
    branches: [ main ]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group test
      - run: uv run playwright install --with-deps chromium
      - run: uv run pytest tests/e2e/ -m e2e --timeout=60
```

---

## §9 Parallel Execution Rules

| Test Layer  | Flag                       | Rationale                                                |
|-------------|----------------------------|----------------------------------------------------------|
| Unit        | `-n auto --dist worksteal` | Fully isolated; no shared state; fast                    |
| Integration | No `-n`                    | Session-scoped containers; DB isolation via transactions |
| E2E         | No `-n`                    | Playwright contexts are per-process                      |

`--dist worksteal` is used (not `loadscope`) because agent chain tests have variable duration and worksteal rebalances
dynamically.

**Worker isolation for parallel unit tests:** all external state uses `fakeredis` (per-function fixture) or
`MemorySaver` (per-function fixture). No module-level singletons permitted.

---

## §10 Parametrize Conventions

### 1. Tabular format for input/output pairs

One `parametrize` call with explicit `ids`:

```python
@pytest.mark.parametrize("url,status", [
    ("https://github.com/owner/repo/issues/1", 202),
    ("http://github.com/owner/repo/issues/1", 422),
], ids=["valid-https", "invalid-http"])
```

### 2. Fixture-based parametrize for fixture files

Never hardcode multi-line test data inline:

```python
@pytest.fixture(params=list(Path("tests/fixtures/issues").glob("*.json")))
def issue_fixture(request: pytest.FixtureRequest) -> dict:
    return json.loads(Path(request.param).read_text())
```

### 3. Indirect parametrize for expensive setups

When LLM response sequences vary per scenario:

```python
@pytest.mark.parametrize("fake_llm", [["approved_json"], ["rejected_json"]], indirect=True)
```

### 4. Named fixtures over boolean flags

Do not parametrize with `True`/`False` when an enum or named fixture conveys intent more clearly.

---

## §11 Forbidden Test Patterns

Per PRD-007 coding rules — tests follow the same discipline as production code:

| Forbidden                                       | Reason                                                    | Alternative                                                       |
|-------------------------------------------------|-----------------------------------------------------------|-------------------------------------------------------------------|
| `isinstance()` / `cast()` / `type()` in tests  | Violates PRD-007                                          | Structural assertion on typed attributes                          |
| `unittest.mock.patch` on module globals         | Breaks DI discipline                                      | `app.dependency_overrides` + fixture injection                    |
| `Any` in test signatures or helper return types | ANN401 enforced                                           | Type all test params and return values explicitly                 |
| `try/except` in test helper functions           | PRD-007 forbids in business logic; tests follow same rule | Let exceptions propagate; use `pytest.raises` for expected errors |
| Local imports inside test functions or fixtures | Obscures dependencies; hides import-cycle problems        | All imports at module top-level                                   |
| Module-level mutable globals in test files      | Breaks parallel worker isolation (`-n auto`)              | Use function-scoped fixtures; no module-level state               |
| Module-level singleton construction at import   | Runs at collection time; pollutes other workers           | Construct inside fixtures; use `autouse` for shared setup         |
| `TYPE_CHECKING` guards                          | PRD-007 forbids                                           | Fix import cycles at the source                                   |
| Inline Redis/Postgres connection strings        | Hardcoded state                                           | Read from env vars; use fixtures                                  |
| `time.sleep()` in tests                         | Flaky by design                                           | `freezegun` for time travel; `asyncio.wait_for` with timeout      |

---

## §12 Verification

After implementation, all of the following must pass locally:

```bash
# Unit tests — isolated, fast
uv run pytest tests/unit/ -n auto --dist worksteal --tb=short

# Coverage gate
uv run pytest tests/unit/ --cov=src --cov-fail-under=80

# Integration tests — requires running Redis + Postgres
uv run pytest tests/integration/ -m integration

# Lint and format
uv run ruff check . && uv run ruff format --check .

# Type check
uv run ty check src/
```

CI matrix must show all jobs green on a PR that adds at least one passing unit test.
