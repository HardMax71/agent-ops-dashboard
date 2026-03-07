---
id: PRD-001-1
title: Goals and Definition of Done
status: DRAFT
domain: product
depends_on: [PRD-001]
---

# PRD-001-1 — Goals & Definition of Done

| Field        | Value                                                  |
|--------------|--------------------------------------------------------|
| Document ID  | PRD-001-1                                              |
| Version      | 1.0                                                    |
| Status       | DRAFT                                                  |
| Date         | March 2026                                             |
| Parent       | [PRD-001 Master Overview](PRD-001-master-overview.md)  |

---

## Goals

Each goal below includes a **Definition of Done** (binary, pass/fail criteria) and a **Verification** step (exact command, UI step, or check to confirm the DoD is met).

---

### Goal 1 — Working multi-agent bug triage system (full LangX stack)

Deliver a functional end-to-end system: a GitHub issue URL goes in, a structured triage report comes out, powered by the full LangChain ecosystem (LCEL, LangGraph, LangServe, LangSmith, LangFlow).

**Definition of Done**

- [ ] A GitHub issue URL submitted via `POST /jobs` produces a job record with status `queued`
- [ ] The LangGraph supervisor starts within 5 seconds and routes to at least one worker agent
- [ ] All 5 worker agents (Investigator, Codebase Searcher, Web Searcher, Critic, Writer) execute successfully on a sample issue
- [ ] The final output contains: `severity`, `root_cause`, `relevant_files` (≥1), `draft_comment`, and `ticket_draft` fields
- [ ] End-to-end wall-clock time is < 3 minutes for a standard GitHub issue

**Verification**

```bash
# Submit a job and poll until done
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"issue_url":"https://github.com/owner/repo/issues/1"}' | jq -r .id)

# Poll status
curl -s http://localhost:8000/jobs/$JOB_ID | jq '{status, output}'

# Assert output fields exist
curl -s http://localhost:8000/jobs/$JOB_ID | jq '
  .output | has("severity") and has("root_cause") and
  has("relevant_files") and has("draft_comment") and has("ticket_draft")
'
# Expected: true
```

---

### Goal 2 — Jira-inspired real-time dashboard (streaming tickets)

The frontend presents submitted jobs as ticket cards. Each ticket updates in real time as agents stream their output — no full-page refresh required.

**Definition of Done**

- [ ] The job queue panel renders submitted jobs as Jira-style cards with status badges (`Queued`, `Running`, `Waiting`, `Done`)
- [ ] Selecting a card opens the live workspace panel with streaming agent output
- [ ] New agent output appears in the UI within 2 seconds of the backend emitting it (SSE latency)
- [ ] Status badge transitions correctly through all states without a page reload
- [ ] UI is functional in Chrome (latest) and Firefox (latest)

**Verification**

1. Start the backend and frontend (`uvicorn main:app` + `npm run dev`)
2. Submit a job via the UI
3. Open Chrome DevTools → Network → filter `text/event-stream`
4. Confirm SSE events arrive; verify the workspace panel updates each time an event fires
5. Run Playwright smoke test: `npx playwright test tests/e2e/streaming.spec.ts`
   - Test asserts that the status badge changes from `Queued` → `Running` → `Done` during a real job
   - Test asserts at least 3 streaming chunks appear in the workspace panel before completion

---

### Goal 3 — Bidirectional human-in-the-loop (agent questions block graph)

An agent can stop mid-execution, surface a clarifying question to the user, and the graph stays paused until the user answers. The answer is injected back and execution resumes from the exact checkpoint.

**Definition of Done**

- [ ] When the supervisor emits a `human_input` node interrupt, job status changes to `waiting`
- [ ] A question card appears in the UI within 2 seconds of the interrupt
- [ ] Submitting an answer via `POST /jobs/{id}/answer` resumes graph execution from the checkpoint (no state is lost)
- [ ] A job with 2 question rounds completes successfully with all prior context retained
- [ ] If the user does not answer within 10 minutes, the job transitions to `timed_out`

**Verification**

```bash
# Trigger a known question-asking scenario (use a test fixture issue)
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"issue_url":"https://github.com/owner/repo/issues/FIXTURE_HITL"}' | jq -r .id)

# Wait for status=waiting
until [ "$(curl -s http://localhost:8000/jobs/$JOB_ID | jq -r .status)" = "waiting" ]; do sleep 2; done

# Answer the question
curl -s -X POST http://localhost:8000/jobs/$JOB_ID/answer \
  -H "Content-Type: application/json" \
  -d '{"answer": "The issue reproduces on Python 3.11 only"}'

# Confirm status returns to running then done
curl -s http://localhost:8000/jobs/$JOB_ID | jq .status
# Expected: "done" (eventually)
```

UI check: Playwright test `tests/e2e/hitl.spec.ts` asserts question card appears and disappears after answer submission.

---

### Goal 4 — Pause / redirect / kill any agent mid-execution

A user can interrupt a running job at any point: pause it (freeze state), redirect it (inject a new instruction into the supervisor), or kill it (terminate cleanly).

**Definition of Done**

- [ ] `POST /jobs/{id}/pause` transitions status to `paused` and the LangGraph worker stops processing new nodes
- [ ] `POST /jobs/{id}/resume` resumes from the last checkpoint without restarting the graph
- [ ] `POST /jobs/{id}/redirect` with a `{"instruction": "..."}` body injects the instruction into the supervisor's next routing decision
- [ ] `POST /jobs/{id}/kill` terminates the ARQ job via `Job.abort()` and sets status to `cancelled`
- [ ] All control actions complete within 3 seconds of the API call
- [ ] The UI exposes Pause, Redirect, and Kill buttons that trigger the respective endpoints

**Verification**

```bash
# Start a job, immediately pause it
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs -d '{"issue_url":"..."}' -H "Content-Type: application/json" | jq -r .id)
curl -s -X POST http://localhost:8000/jobs/$JOB_ID/pause | jq .status
# Expected: "paused"

# Resume
curl -s -X POST http://localhost:8000/jobs/$JOB_ID/resume | jq .status
# Expected: "running"

# Kill
curl -s -X POST http://localhost:8000/jobs/$JOB_ID/kill | jq .status
# Expected: "cancelled"
```

Run `pytest tests/integration/test_job_control.py -v` — all 6 control action tests must pass.

---

### Goal 5 — LangSmith instrumentation (tracing, eval, cost)

Every agent call, LangGraph node transition, and LCEL chain execution is automatically traced in LangSmith. A LangSmith deep-link appears on each job card. Cost and latency metrics are queryable.

**Definition of Done**

- [ ] `LANGCHAIN_TRACING_V2=true` is set; every job produces a LangSmith trace with a unique `run_id`
- [ ] The trace tree shows LCEL chain internals (prompt, LLM call, output parser) as child spans
- [ ] LangGraph node transitions appear as named spans in the trace
- [ ] Each job record in the DB contains a `langsmith_url` field pointing to the trace
- [ ] The UI job card renders a "View in LangSmith" link that opens the correct trace
- [ ] At least one eval dataset exists in LangSmith with ≥ 10 reference examples
- [ ] Running `langsmith evaluate` on the dataset produces a score and stores it in LangSmith

**Verification**

```bash
# Confirm trace is created after a job
JOB=$(curl -s http://localhost:8000/jobs/$JOB_ID)
echo $JOB | jq .langsmith_url
# Expected: non-empty URL like https://smith.langchain.com/...

# Open the URL — verify trace tree shows child spans
# (Manual: open URL in browser, confirm LCEL and LangGraph spans are visible)

# Run evals
python scripts/run_evals.py --dataset bug_triage_v1
# Expected: prints eval results with score >= 4.0 / 5.0
```

---

### Goal 6 — LangFlow as visual prototyping layer

Each agent chain is first designed in LangFlow before being committed to code. LangFlow serves as the live configuration UI for non-technical users to adjust agent prompts and model settings.

**Definition of Done**

- [ ] LangFlow is running at `http://localhost:7860` (Docker or `langflow run`)
- [ ] Each of the 5 worker agent chains has a saved LangFlow flow file in `langflow/flows/`
- [ ] Exporting a flow from LangFlow and running it produces the same output as the Python LCEL implementation (within LLM variance)
- [ ] LangFlow configuration UI is linked from the main dashboard ("Configure Agents" nav item)

**Verification**

```bash
# Start LangFlow
langflow run --port 7860

# Verify flow files exist
ls langflow/flows/
# Expected: investigator.json, codebase_search.json, web_search.json, critic.json, writer.json

# Run flow via LangFlow API and compare to LangServe endpoint
python scripts/compare_flow_vs_langserve.py --agent investigator --input tests/fixtures/sample_issue.json
# Expected: both outputs have the same top-level keys; no assertion errors
```

UI check: navigate to `http://localhost:3000` → "Configure Agents" → verify LangFlow iframe or link is reachable.

---

### Goal 7 — LangServe microservice deployment per agent chain

Each finalized agent chain is deployed as an independent LangServe HTTP endpoint. The LangGraph supervisor calls these endpoints as tools over HTTP.

**Definition of Done**

- [ ] All 5 LangServe endpoints are running and pass their `/health` checks:
  - `POST /agents/investigator/invoke`
  - `POST /agents/codebase-search/invoke`
  - `POST /agents/web-search/invoke`
  - `POST /agents/critic/invoke`
  - `POST /agents/writer/invoke`
- [ ] Each endpoint returns a valid structured response within 60 seconds for a sample input
- [ ] The LangGraph supervisor successfully calls all 5 endpoints during a real job (confirmed via LangSmith trace)
- [ ] Each endpoint has its own Docker service in `docker-compose.yml`

**Verification**

```bash
# Health checks
for agent in investigator codebase-search web-search critic writer; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/agents/$agent/health)
  echo "$agent: $STATUS"
done
# Expected: all 200

# Invoke investigator with sample input
curl -s -X POST http://localhost:8001/agents/investigator/invoke \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_issue.json | jq .output
# Expected: non-empty object with investigation fields

# Docker services running
docker compose ps | grep agent
# Expected: 5 agent service rows, all "Up"
```

---

### Goal 8 — Portfolio-grade production quality

The codebase demonstrates professional engineering standards: typed, tested, linted, documented, and deployable via Docker Compose with a one-command setup.

**Definition of Done**

- [ ] All Python files pass `ruff check` and `ty check` with zero errors
- [ ] Test coverage ≥ 80% (`pytest --cov`)
- [ ] `docker compose up` starts all services successfully with no manual steps beyond setting `.env`
- [ ] `mkdocs build` completes with zero warnings
- [ ] All PRD documents are published and navigable via MkDocs
- [ ] A `README.md` exists with: project description, architecture diagram, quickstart (≤5 steps), and links to docs
- [ ] The repo has CI (GitHub Actions) running lint + tests on every PR

**Verification**

```bash
# Lint
ruff check . && echo "ruff: OK"
ty check . && echo "ty: OK"

# Tests
pytest --cov=src --cov-report=term-missing
# Expected: coverage >= 80%

# Docker
docker compose up -d
docker compose ps
# Expected: all services Up, no Exit codes

# Docs
cd docs && mkdocs build
# Expected: "INFO - Documentation built successfully" with 0 warnings
```

CI check: open the GitHub Actions tab on the PR — all checks must be green.

---

## Non-Goals (v1.0)

The following are explicitly out of scope for v1.0 and are tracked in the [v2 roadmap](../plans/roadmap-v2.md).

| Non-Goal                                        | Reason deferred                                               |
|-------------------------------------------------|---------------------------------------------------------------|
| Support for non-GitHub trackers (Jira, Linear, GitLab) | Adds auth/API complexity; GitHub covers the core demo use case |
| Fully autonomous operation (zero human oversight) | Safety and trust require human-in-the-loop for v1            |
| Non-software-dev domains                        | Domain-specific tooling and prompts need separate PRDs        |
| Real-time multi-user collaborative sessions     | Requires session isolation and conflict-resolution logic      |
| Mobile interface                                | Desktop-first; mobile layout deferred post-MVP                |
| Self-hosted LLM support (Ollama, etc.)          | API compatibility and performance tuning are non-trivial      |
