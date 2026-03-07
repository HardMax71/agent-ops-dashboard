---
id: roadmap-v1
title: Release Roadmap v1 (Precise)
status: DRAFT
domain: planning
depends_on: [PRD-001]
---

# Roadmap v1 — Precise Delivery Plan

| Field   | Value                                                  |
|---------|--------------------------------------------------------|
| Version | v1.0                                                   |
| Status  | DRAFT                                                  |
| Date    | March 2026                                             |
| Parent  | [PRD-001 Master Overview](../prd/PRD-001-master-overview.md) |

This document is the authoritative, week-precise delivery plan for AgentOps Dashboard v1.0.
Each phase lists concrete deliverables, binary acceptance criteria per deliverable, and an **exit gate** —
the set of conditions that must all pass before the next phase begins.

---

## Phase 1 — Core Loop

**Target: Weeks 1–3**

### Deliverables

- **D1.1** Project scaffolding
  - `pyproject.toml` with `uv` workspace, `ruff`, `ty`, `pytest` configured
  - Docker Compose file with placeholder services
  - GitHub Actions CI running lint + test on push
  - `README.md` with quickstart skeleton

- **D1.2** Single Investigator LCEL chain
  - `InvestigatorChain`: `ChatPromptTemplate | ChatOpenAI.with_structured_output(InvestigatorOutput)`
  - Output model: `InvestigatorOutput(summary: str, hypotheses: list[str], files_to_check: list[str])`
  - Unit tests covering happy path and malformed LLM output fallback

- **D1.3** LangGraph skeleton (single-agent)
  - `StateGraph` with nodes: `supervisor`, `investigator`, `writer`, `END`
  - `AgentState` TypedDict with: `issue_url`, `messages`, `agent_outputs`, `status`
  - Supervisor routing logic (stub: always routes to investigator then writer)
  - SQLite checkpointer configured

- **D1.4** LangSmith tracing active
  - `LANGCHAIN_TRACING_V2=true` in `.env.example`
  - Every chain call produces a trace with project name `agent-ops-v1`
  - Trace has named spans for prompt, LLM call, and parser

- **D1.5** Minimal FastAPI job endpoint
  - `POST /jobs` — creates a job record (SQLite), enqueues via ARQ, returns `{id, status}`
  - `GET /jobs/{id}` — returns job record with current status
  - Pydantic v2 request model: `CreateJobRequest(issue_url: HttpUrl)`

### Acceptance Criteria

| Deliverable | Criterion |
|-------------|-----------|
| D1.1 | `ruff check .` exits 0; `pytest` passes; `docker compose up` starts without error |
| D1.2 | `pytest tests/unit/test_investigator_chain.py` passes all cases including output validation |
| D1.3 | Running `python -m src.graph.run --issue-url <url>` completes and prints `AgentState.agent_outputs` |
| D1.4 | LangSmith UI shows a trace with ≥3 nested spans after running D1.3 |
| D1.5 | `curl -X POST /jobs -d '{"issue_url":"..."}'` returns `200` with `id` and `status: queued` |

### Exit Gate (Phase 1 → Phase 2)

All of the following must be true:

- [ ] D1.1–D1.5 acceptance criteria all pass
- [ ] A real GitHub issue (not a fixture) produces a non-empty `InvestigatorOutput`
- [ ] LangSmith trace is visible for the real-issue run
- [ ] CI is green on `main`

---

## Phase 2 — Multi-Agent

**Target: Weeks 4–5**

### Deliverables

- **D2.1** Full agent suite (5 LCEL chains)
  - `CodebaseSearchChain`: semantic search over embedded repo (Chroma + `text-embedding-3-small`)
  - `WebSearchChain`: Tavily API tool integrated into LCEL chain
  - `CriticChain`: reviews prior agent outputs, outputs `CriticOutput(issues: list[str], verdict: Literal["pass","revise"])`
  - `WriterChain`: produces `WriterOutput(severity, root_cause, relevant_files, draft_comment, ticket_draft)`

- **D2.2** LangServe endpoints (one per chain)
  - `POST /agents/investigator/invoke`
  - `POST /agents/codebase-search/invoke`
  - `POST /agents/web-search/invoke`
  - `POST /agents/critic/invoke`
  - `POST /agents/writer/invoke`
  - Each endpoint has `/health` returning `200 {"status": "ok"}`
  - Each agent service has its own `Dockerfile` and entry in `docker-compose.yml`

- **D2.3** Supervisor routing logic (full)
  - Supervisor reads `AgentState` and decides next agent via LLM-powered routing
  - Routing respects dependency order: investigator and codebase-search before critic; critic before writer
  - `max_iterations` guard: terminates after 10 supervisor decisions

- **D2.4** Shared state flowing through all nodes
  - `AgentState` carries accumulated `agent_outputs` across all nodes
  - Each worker reads relevant prior outputs from state before calling its chain
  - Final writer node has access to all prior outputs

### Acceptance Criteria

| Deliverable | Criterion |
|-------------|-----------|
| D2.1 | `pytest tests/unit/test_*_chain.py` passes for all 5 chains |
| D2.2 | `curl /agents/investigator/health` → 200; `curl /agents/writer/invoke` with fixture input → valid `WriterOutput` JSON |
| D2.3 | Running the full graph on a fixture issue routes through ≥3 distinct agents before reaching writer |
| D2.4 | `WriterOutput.relevant_files` contains files identified by `CodebaseSearchChain` in the same run |

### Exit Gate (Phase 2 → Phase 3)

All of the following must be true:

- [ ] D2.1–D2.4 acceptance criteria all pass
- [ ] Full 5-agent run completes end-to-end in < 3 minutes on a real GitHub issue
- [ ] LangSmith trace shows all 5 agent spans under the supervisor span
- [ ] All 5 Docker services start cleanly via `docker compose up`
- [ ] CI green on `main`

---

## Phase 3 — Human-in-the-Loop

**Target: Week 6**

### Deliverables

- **D3.1** `interrupt()` nodes in LangGraph
  - `human_input` node added to the graph with `interrupt_before` configuration
  - Supervisor can route to `human_input` when confidence is below threshold
  - Interrupt stores the question in `AgentState.pending_question`

- **D3.2** Job control endpoints
  - `POST /jobs/{id}/answer` — injects user answer and calls `graph.update_state()` to resume
  - `POST /jobs/{id}/pause` — sets Redis flag checked by worker before each node
  - `POST /jobs/{id}/resume` — clears pause flag
  - `POST /jobs/{id}/redirect` — injects instruction into supervisor's next routing context
  - `POST /jobs/{id}/kill` — calls `Job.abort()` on the ARQ job, sets status `cancelled`

- **D3.3** Checkpoint persistence (Postgres)
  - Migrate checkpointer from SQLite to Postgres for production durability
  - `AsyncPostgresSaver` configured in graph builder
  - Graph state survives a worker process restart mid-job

- **D3.4** Timeout handling
  - Jobs in `waiting` status for > 10 minutes automatically transition to `timed_out`
  - ARQ scheduled task runs every minute to enforce timeout

### Acceptance Criteria

| Deliverable | Criterion |
|-------------|-----------|
| D3.1 | Running fixture `FIXTURE_HITL` issue causes job status to reach `waiting` with non-empty `pending_question` |
| D3.2 | `pytest tests/integration/test_job_control.py` passes all 6 control action tests |
| D3.3 | Killing and restarting the worker mid-job, then calling `/resume`, completes the job successfully |
| D3.4 | A job left in `waiting` for 10+ minutes (mocked clock) transitions to `timed_out` |

### Exit Gate (Phase 3 → Phase 4)

All of the following must be true:

- [ ] D3.1–D3.4 acceptance criteria all pass
- [ ] A human-in-the-loop round-trip (question → answer → completion) works on a real issue
- [ ] Pause → resume preserves all agent outputs accumulated before the pause
- [ ] Kill leaves no orphaned ARQ jobs (confirmed via ARQ dashboard or `arq.inspect`)

---

## Phase 4 — Backend API

**Target: Weeks 7–8**

### Deliverables

- **D4.1** SSE streaming endpoint
  - `GET /jobs/{id}/stream` returns `Content-Type: text/event-stream`
  - Events: `{"type": "agent_output", "agent": "...", "chunk": "..."}` and `{"type": "status_change", "status": "..."}`
  - Redis Pub/Sub used for fanout (worker publishes → API subscribes → SSE to client)
  - Connection drops reconnect within ~2 s; **missed events are not replayed** — Pub/Sub has no history (gapless resume via `Last-Event-ID` is a v2 concern requiring Redis Streams or a DB-backed event log)

- **D4.2** Job persistence layer
  - Postgres table `jobs`: `id`, `issue_url`, `status`, `created_at`, `updated_at`, `output`, `langsmith_url`
  - SQLAlchemy async ORM models
  - Alembic migrations for schema

- **D4.3** GitHub API integration
  - `GET /repos/{owner}/{repo}/issues/{number}` called on job creation to fetch issue body, labels, author
  - Issue data stored in `AgentState.issue_context`
  - GitHub OAuth token passed via `Authorization: Bearer` header on API calls

- **D4.4** API hardening
  - Rate limiting: max 10 concurrent jobs per user
  - Input validation: `issue_url` must match `github.com/{owner}/{repo}/issues/{number}` pattern
  - OpenAPI docs auto-generated and accessible at `/docs`
  - All endpoints return structured error responses `{"error": {"code": ..., "message": ...}}`

### Acceptance Criteria

| Deliverable | Criterion |
|-------------|-----------|
| D4.1 | `curl -N /jobs/{id}/stream` outputs ≥5 SSE events during a real job run; connection drop reconnects within 2 s and stream resumes from the live position (no historical replay) |
| D4.2 | `alembic upgrade head` runs cleanly; job survives an API server restart (fetched from Postgres) |
| D4.3 | Job state contains `issue_context.body` and `issue_context.labels` populated from the real GitHub API |
| D4.4 | `curl -X POST /jobs -d '{"issue_url":"https://not-github.com/x"}'` returns `422`; `/docs` loads without error |

### Exit Gate (Phase 4 → Phase 5)

All of the following must be true:

- [ ] D4.1–D4.4 acceptance criteria all pass
- [ ] `pytest tests/integration/test_api.py` fully green
- [ ] SSE stream tested with a real browser `EventSource` connection (manual check)
- [ ] Alembic migration is idempotent (`upgrade head` run twice produces no error)

---

## Phase 5 — React UI

**Target: Weeks 9–11**

### Deliverables

- **D5.1** Job queue panel (Jira-style)
  - Left sidebar: list of job cards with `issue_url` title, status badge, creation time
  - Status badge colors: grey (Queued), blue (Running), amber (Waiting), purple (Paused), green (Done), red (Cancelled), dark-red (Timed Out)
  - "New Job" button opens a modal with `issue_url` input and Submit

- **D5.2** Live workspace panel
  - Center panel opens when a job card is selected
  - Streaming agent output rendered in real time via `EventSource`
  - Per-agent section headers with agent name and status indicator
  - Auto-scrolls to latest output; user can scroll up to read history

- **D5.3** Question cards (human-in-the-loop UI)
  - When job status is `waiting`, a question card appears above the workspace
  - Card shows the agent's question and a free-text answer input
  - Submitting the answer calls `POST /jobs/{id}/answer` and dismisses the card
  - Card is visually distinct (amber border, "Agent needs your input" label)

- **D5.4** Output panel
  - Right panel shows the final `WriterOutput` when job status is `done`
  - Fields: Severity badge, Root Cause, Relevant Files (file links), Draft Comment (editable), Ticket Draft (editable)
  - "Post to GitHub" button (calls write-back endpoint — stubbed in Phase 5, live in Phase 6)

- **D5.5** Agent control bar
  - Appears at the top of the workspace when a job is `running` or `paused`
  - Buttons: Pause / Resume, Redirect (opens text input), Kill
  - Each button calls the respective control endpoint and updates the UI state

### Acceptance Criteria

| Deliverable | Criterion |
|-------------|-----------|
| D5.1 | Submitting a job via the UI creates a card that appears in the queue without page refresh |
| D5.2 | Agent output chunks appear in the workspace < 2s after backend emits them (measure with browser DevTools) |
| D5.3 | Question card appears when job reaches `waiting`; submitting answer causes card to disappear and job to resume |
| D5.4 | Output panel renders all 5 fields when job reaches `done`; edits to Draft Comment persist in component state |
| D5.5 | Clicking Pause → badge changes to `paused`; clicking Resume → badge returns to `running` |

### Exit Gate (Phase 5 → Phase 6)

All of the following must be true:

- [ ] D5.1–D5.5 acceptance criteria all pass
- [ ] Playwright E2E tests pass: `npx playwright test tests/e2e/`
- [ ] UI tested in Chrome and Firefox (latest versions)
- [ ] Lighthouse accessibility score ≥ 80 on the main dashboard page
- [ ] No console errors during a full job lifecycle in the browser

---

## Phase 6 — Polish

**Target: Weeks 12–13**

### Deliverables

- **D6.1** GitHub write-back
  - "Post to GitHub" button calls `POST /jobs/{id}/publish`
  - Backend calls `POST /repos/{owner}/{repo}/issues/{number}/comments` with `draft_comment`
  - Backend calls `PATCH /repos/{owner}/{repo}/issues/{number}` to add severity label
  - Result URL is stored on the job and displayed in the output panel

- **D6.2** LangSmith evaluation suite
  - Eval dataset `bug_triage_v1` created in LangSmith with ≥ 10 reference examples
  - Evaluator script `scripts/run_evals.py` runs the full graph on dataset and submits results
  - Metrics tracked: `helpfulness` (LLM judge, 1–5), `file_relevance` (overlap with reference), `severity_match` (exact match)
  - Eval results visible in LangSmith Experiments tab

- **D6.3** Codebase vector index
  - On job creation, if repo not already indexed: clone repo, chunk Python files, embed with `text-embedding-3-small`, store in Chroma
  - Index stored persistently in `data/chroma/{owner}-{repo}/`
  - `CodebaseSearchChain` queries the index with `k=5` results
  - Re-indexing triggered if repo has new commits since last index (checked via GitHub API)

- **D6.4** LangFlow configuration UI
  - LangFlow running as a Docker service at `/langflow`
  - Flow files for all 5 agents checked into `langflow/flows/`
  - Dashboard "Configure Agents" nav item opens the LangFlow UI
  - Non-technical user can change the system prompt of any agent and save (flow re-exported to `langflow/flows/`)

### Acceptance Criteria

| Deliverable | Criterion |
|-------------|-----------|
| D6.1 | Clicking "Post to GitHub" on a completed job creates a real comment on the GitHub issue (verified manually on a test repo) |
| D6.2 | `python scripts/run_evals.py --dataset bug_triage_v1` exits 0 and prints an aggregate `helpfulness` score ≥ 4.0 / 5.0 |
| D6.3 | Second job on the same repo uses cached index (confirmed: no re-clone in logs); `CodebaseSearchChain` returns ≥1 relevant file for a known fixture issue |
| D6.4 | LangFlow UI accessible at `/langflow`; modifying a system prompt in LangFlow and running the graph produces output reflecting the change |

### Exit Gate (Phase 6 = v1.0 Release)

All of the following must be true:

- [ ] D6.1–D6.4 acceptance criteria all pass
- [ ] All Phase 1–5 exit gates remain satisfied (run full regression)
- [ ] `mkdocs build` exits 0 with no warnings
- [ ] `docker compose up` starts all services in < 60 seconds on a fresh clone with only `.env` configured
- [ ] LangSmith eval score ≥ 4.0 / 5.0 on `bug_triage_v1` dataset
- [ ] README is complete with architecture diagram, quickstart, and links to deployed docs
- [ ] All PRD documents published and linked from the MkDocs nav
