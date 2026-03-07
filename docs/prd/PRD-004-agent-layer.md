---
id: PRD-004
title: Agent Layer — LangChain, LCEL, LangServe & LangFlow
status: DRAFT
domain: backend/agents
depends_on: [PRD-001, PRD-003, PRD-005]
key_decisions: [lcel-chain-pattern, langserve-microservices, langflow-prototyping-workflow, chroma-vector-index, agent-finding-base-contract]
---

# PRD-004 — Agent Layer: LangChain, LCEL, LangServe & LangFlow

| Field        | Value                                            |
|--------------|--------------------------------------------------|
| Document ID  | PRD-004                                          |
| Version      | 1.0                                              |
| Status       | DRAFT                                            |
| Date         | March 2026                                       |
| Parent Doc   | [PRD-001](PRD-001-master-overview.md)            |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md) (Orchestration), [PRD-005](PRD-005-langsmith-observability.md) (Observability) |

---

## Overview

> **Detailed specs:** [Full LCEL Chain Specs](PRD-004-1-agent-chains.md) ·
> [Codebase Vector Index](PRD-004-2-codebase-index.md)

This document covers the **individual agent layer** — the internals of each of the five specialized worker agents. These
agents are the leaves of the system: the LangGraph supervisor ([PRD-003](PRD-003-langgraph-orchestration.md)) calls them, but doesn't know or care what's
inside.

Each agent follows the same lifecycle:

1. **Designed and tested visually in LangFlow** (prototyping)
2. **Implemented as an LCEL chain** in Python using LangChain primitives
3. **Deployed as a LangServe endpoint** — an independent HTTP microservice
4. **Called by the LangGraph supervisor** via HTTP during job execution

This separation is intentional. Agents are independently swappable, versioned, and testable without touching the
orchestration layer.

---

## LangChain + LCEL — Agent Internals

### Why LCEL

Every agent's core logic is an LCEL (LangChain Expression Language) chain. LCEL is chosen over the legacy `LLMChain`
approach because:

- **Streaming by default** — every LCEL chain supports `astream()`, which LangServe exposes automatically
- **Async by default** — critical for running multiple agents concurrently
- **Composable** — complex agents (like Codebase Search with RAG) can be built by piping components cleanly
- **LangSmith integration** — LCEL chains are automatically traced without any additional instrumentation code
- **Parallel execution** — `RunnableParallel` lets agents fetch context from multiple sources simultaneously

### Standard LCEL Chain Pattern

Every agent in this system follows this base pattern:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

prompt = ChatPromptTemplate.from_messages([
    ("system", AGENT_SYSTEM_PROMPT),
    ("human", AGENT_HUMAN_TEMPLATE),
])

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    base_url=settings.model_gateway_url,  # e.g. http://litellm:4000
    api_key=settings.service_token,        # internal token, not the OpenAI key
)

chain = prompt | llm.with_structured_output(AgentOutputSchema)
```

`with_structured_output()` uses the model's native function-calling / JSON mode to enforce the
schema. Do not use `PydanticOutputParser` — it requires explicit format instructions in the prompt
and is fragile with complex nested schemas.

The `chain` object is what gets served via LangServe.

### LCEL Features Used Per Agent

| Feature               | Agents          | Purpose                                                      |
|-----------------------|-----------------|--------------------------------------------------------------|
| `RunnableParallel`    | Codebase Search | Fetches vector store results and issue body simultaneously   |
| `RunnablePassthrough` | All             | Passes through input fields that the prompt needs unchanged  |
| `RunnableLambda`      | Writer          | Custom post-processing to format the GitHub comment markdown |
| `.with_retry()`       | All             | Automatic retry on LLM rate limits (max 3 attempts)          |
| `.with_fallbacks()`   | All             | Falls back from GPT-4o to GPT-4o-mini on repeated failures   |
| `.astream()`          | All             | Enables token-by-token streaming through LangServe           |

---

## LangServe — Agent Microservices

### Architecture Decision

> **LangServe status (March 2026):** LangServe is in maintenance mode. The LangChain team recommends
> LangGraph Platform for new projects and will not accept new feature contributions to LangServe
> (source: github.com/langchain-ai/langserve README). This project continues to use LangServe because
> it provides a stable, simple REST interface for LCEL runnables and our use case does not require
> LangGraph Platform's additional features. Pin `langserve>=0.3,<0.4` in `pyproject.toml` to prevent
> unintended upgrades.

Rather than importing agent functions directly into the LangGraph process, each agent is deployed as a **standalone
FastAPI + LangServe microservice**. The LangGraph nodes call these services over HTTP.

Benefits:

- Each agent is independently deployable and restartable
- Agent prompts, models, and logic can be updated without redeploying the orchestration layer
- Horizontal scaling: a heavy agent (like Codebase Search) can be scaled independently
- Clear ownership boundary: a team member can "own" one agent service
- The agent config UI (Zone 3 settings) just stores endpoint URLs — fully pluggable

### Service Registry

| Service Name               | Default Port | Endpoint                  | Description                            |
|----------------------------|--------------|---------------------------|----------------------------------------|
| `agentops-investigator`    | 8001         | `/agents/investigator`    | Reads and interprets GitHub issues     |
| `agentops-codebase-search` | 8002         | `/agents/codebase-search` | Semantic search over repository code   |
| `agentops-web-search`      | 8003         | `/agents/web-search`      | Web search for errors and stack traces |
| `agentops-critic`          | 8004         | `/agents/critic`          | Reviews findings for correctness       |
| `agentops-writer`          | 8005         | `/agents/writer`          | Produces final structured report       |

### LangServe Setup Pattern

Each service uses the same setup pattern:

```python
# agent_service/server.py
from functools import lru_cache
from pydantic_settings import BaseSettings
from fastapi import FastAPI
from langserve import add_routes
from .chain import chain


class Settings(BaseSettings):
    enable_playground: bool = False  # ENABLE_PLAYGROUND=true to opt in (dev only)
    model_gateway_url: str   # e.g. http://litellm:4000
    service_token: str       # unique per service, validated by gateway


@lru_cache
def get_settings() -> Settings:
    return Settings()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AgentOps — Investigator Agent")

    # playground_type=None removes /playground from the router at registration time.
    # "default" re-enables it only when ENABLE_PLAYGROUND=true.
    add_routes(
        app,
        chain,
        path="/agents/investigator",
        playground_type="default" if settings.enable_playground else None,
        enable_feedback_endpoint=True,
    )
    return app


app = create_app()
```

LangServe automatically generates:

- `POST /agents/investigator/invoke` — single synchronous call
- `POST /agents/investigator/stream` — streaming response
- `POST /agents/investigator/batch` — batch processing
- `GET  /agents/investigator/playground` — interactive testing UI

### LangServe Playground

Each LangServe endpoint comes with a built-in `/playground` UI at no extra cost. This is used during development to
manually test agent behavior with real GitHub issues before running full end-to-end jobs. This complements the LangFlow
prototyping workflow.

**Security requirement:** The `/playground` route must be disabled in staging and production. LangServe exposes the
playground by default; it is disabled by passing `playground_type=None` to `add_routes()`, which removes the route
from the FastAPI router at registration time — no middleware or network rule required. The `ENABLE_PLAYGROUND`
environment variable (default: `false`) controls this via a `pydantic-settings` `BaseSettings` class; the value is
read inside `create_app()` so no module-level globals are introduced. `ENABLE_PLAYGROUND=true` must only appear in
local development environments. In staging, if playground access is required for debugging, the service must be
redeployed with `ENABLE_PLAYGROUND=true` behind an internal network or VPN — it must never be reachable from the
public internet.

### Model Gateway

Each LangServe service does **not** hold an OpenAI API key. Instead, all five services authenticate
to a shared model gateway (LiteLLM proxy). The gateway is the only component that holds the real
`OPENAI_API_KEY`.

**Why:**
- **Single key surface** — rotate or revoke in one place; no per-service key management
- **Unified rate limiting and spend cap** — LiteLLM enforces a single RPM/TPM budget across all agents
- **Audit log** — every LLM call is logged centrally with the originating service token
- **Key isolation** — a compromised agent service can only call the gateway with its own service token,
  which can be revoked without cycling the OpenAI key

**Authentication flow:**

Each service is issued a unique `SERVICE_TOKEN` environment variable. The gateway validates this
token and forwards the request to OpenAI using the real API key.

| Service                    | Service Token Env Var                  |
|----------------------------|----------------------------------------|
| `agentops-investigator`    | `GATEWAY_TOKEN_INVESTIGATOR`           |
| `agentops-codebase-search` | `GATEWAY_TOKEN_CODEBASE_SEARCH`        |
| `agentops-web-search`      | `GATEWAY_TOKEN_WEB_SEARCH`             |
| `agentops-critic`          | `GATEWAY_TOKEN_CRITIC`                 |
| `agentops-writer`          | `GATEWAY_TOKEN_WRITER`                 |

**Configuration in each service:**

```python
class Settings(BaseSettings):
    enable_playground: bool = False
    model_gateway_url: str   # e.g. http://litellm:4000
    service_token: str       # unique per service, validated by gateway
```

The `ChatOpenAI` client in each LCEL chain is initialized with `base_url=settings.model_gateway_url`
and `api_key=settings.service_token`. LiteLLM's OpenAI-compatible API surface means no other code
changes are needed.

**Gateway deployment:** The LiteLLM proxy runs as a sixth Docker service (`agentops-model-gateway`,
port 4000). It is the only container with `OPENAI_API_KEY` in its environment. It is not exposed
externally — only reachable within the Docker network.

---

## LangFlow — Prototyping Workflow

### Role in Development Process

LangFlow is the **first stop for any new agent or prompt change**. The development workflow is:

```
1. DESIGN in LangFlow
   ↓  Drag components, connect them, test with real issue data
   ↓  Iterate on system prompt, try different models, test edge cases

2. EXPORT from LangFlow
   ↓  Export the flow as Python code (LangFlow supports LCEL export)
   ↓  Refine the exported code, add Pydantic output schemas

3. DEPLOY via LangServe
   ↓  Wrap the chain in a LangServe FastAPI app
   ↓  Run locally, validate via /playground

4. EVALUATE in LangSmith
   ↓  Run against golden dataset, check scores
   ↓  If failing: back to step 1 in LangFlow
```

LangFlow prevents wasted engineering time. A prompt that fails visually in LangFlow won't get deployed to LangServe.

### Agent Configuration UI

In v1.1, the Settings page of AgentOps Dashboard will embed LangFlow's canvas (via iframe or the LangFlow API). This
allows users to:

- Visually modify an agent's prompt, model, or chain structure
- Test the modified chain against a sample issue before saving
- Push the updated chain to the LangServe endpoint

This is the product's equivalent of a "plugin editor" — power users can customize agent behavior without writing code.

### What Gets Prototyped in LangFlow

| Agent           | LangFlow Prototype Focus                                                               |
|-----------------|----------------------------------------------------------------------------------------|
| Investigator    | System prompt calibration — how structured should the hypothesis be?                   |
| Codebase Search | RAG retriever settings — chunk size, k, similarity threshold                           |
| Web Search      | Tavily query formulation — how to turn an issue into a good search query               |
| Critic          | Scoring rubric — what makes a finding "confident enough" vs "needs more investigation" |
| Writer          | Output format — structured report vs. free-form markdown; GitHub comment tone          |

---

## Agent Specifications

### Investigator Agent

**Purpose:** First agent to run. Reads the full GitHub issue body and forms an initial hypothesis about the bug's
nature, affected areas, and likely root cause.

**Input:**

```python
class InvestigatorInput(BaseModel):
    issue_title: str
    issue_body: str
    prior_findings: list[dict] = []
```

**Output:**

```python
class InvestigatorFinding(AgentFindingBase):
    hypothesis: str
    affected_areas: list[str]
    keywords_for_search: list[str]
    error_messages: list[str]
```

**LCEL Chain:**

```python
chain = (
        investigator_prompt
        | llm.with_structured_output(InvestigatorFinding)
)
```

**Model:** GPT-4o-mini (sufficient for issue interpretation; cost-effective)

**Tools:** None — this agent only reads its inputs, no external tool calls

---

### Codebase Search Agent

**Purpose:** Searches the repository's source code for files and code snippets relevant to the bug. Uses semantic vector
search against a pre-built Chroma index of the repository.

**Input:**

```python
class CodebaseSearchInput(BaseModel):
    repository: str
    keywords: list[str]
    hypothesis: str
    affected_areas: list[str]
```

**Output:**

```python
class CodebaseFinding(AgentFindingBase):
    relevant_files: list[RelevantFile]
    root_cause_location: str | None
```

**LCEL Chain (with RAG):**

```python
chain = (
        RunnableParallel({
            "context": codebase_retriever,  # Chroma vector store
            "hypothesis": RunnablePassthrough(),
            "keywords": RunnablePassthrough(),
        })
        | codebase_search_prompt
        | llm.with_structured_output(CodebaseFinding)
)
```

**Model:** GPT-4o (larger context needed for code comprehension)

**Tools:** Chroma vector store retriever (see Section 6)

---

### Web Search Agent

**Purpose:** Searches the web for the error messages, stack traces, and library issues mentioned in the GitHub issue.
Particularly useful for third-party library bugs and environment-specific errors.

**Input:**

```python
class WebSearchInput(BaseModel):
    error_messages: list[str]  # from Investigator
    issue_title: str
    affected_areas: list[str]
```

**Output:**

```python
class WebSearchFinding(AgentFindingBase):
    relevant_results: list[WebResult]
    external_root_cause: str | None
```

**LCEL Chain (with tool):**

```python
from langchain_tavily import TavilySearch

tavily = TavilySearch(max_results=5)
llm_with_tools = llm.bind_tools([tavily])

chain = (
        web_search_prompt
        | llm_with_tools
        | tool_executor  # executes the Tavily search
        | web_result_prompt
        | llm.with_structured_output(WebSearchFinding)
)
```

**Model:** GPT-4o-mini

**Tools:** Tavily Search API

---

### Critic Agent

**Purpose:** Reviews the accumulated findings from other agents and challenges weak hypotheses. Outputs a revised
confidence score and flags gaps that need more investigation.

**Input:**

```python
class CriticInput(BaseModel):
    all_findings: list[dict]  # all AgentFindings so far
    current_hypothesis: str
    codebase_evidence: list[str]  # code snippets supporting hypothesis
```

**Output:**

```python
class CritiqueFinding(AgentFindingBase):
    verdict: Literal["CONFIRMED", "UNCERTAIN", "CHALLENGED"]
    confidence_adjustment: float
    gaps: list[str]
    revised_hypothesis: str | None
    ready_for_report: bool
```

**LCEL Chain:**

```python
chain = (
        critic_prompt
        | llm.with_structured_output(CritiqueFinding)
)
```

**Model:** GPT-4o (adversarial reasoning benefits from a stronger model)

**Tools:** None

---

### Writer Agent

**Purpose:** Takes all accumulated findings and produces the final structured outputs: triage report, GitHub comment
draft, and ticket draft.

**Input:**

```python
class WriterInput(BaseModel):
    all_findings: list[dict]
    human_exchanges: list[dict]  # Q&A with user incorporated into report
    issue_title: str
    issue_url: str
    repository: str
```

**Output:**

```python
class WriterOutput(AgentFindingBase):
    report: TriageReport  # structured severity/root cause/files
    github_comment_markdown: str  # ready to post to GitHub
    ticket_title: str
    ticket_labels: list[str]
    ticket_assignee_suggestion: str
    ticket_effort_estimate: str  # XS / S / M / L / XL
```

**LCEL Chain:**

```python
chain = (
        RunnableParallel({
            "report": report_chain,  # generates TriageReport
            "comment": comment_chain,  # generates GitHub markdown comment
            "ticket": ticket_chain,  # generates ticket fields
        })
        | merge_outputs_lambda  # RunnableLambda to merge into WriterOutput
)
```

**Model:** GPT-4o (quality of final output matters most here)

**Tools:** None — pure generation from accumulated context

---

## Codebase Vector Index

### Purpose

The Codebase Search Agent needs semantic search over the repository's source code. A keyword-based search is
insufficient for finding the code path related to "JWT token expiry on UTC server" when the actual code says
`if token.exp < time.time()`.

### Implementation

```
Repository Clone → Code Chunking → Embedding → Chroma Vector Store
```

- **Chunking:** `RecursiveCharacterTextSplitter` with `chunk_size=1000`, `chunk_overlap=200`, splitting on Python/JS/TS
  syntax boundaries
- **Embedding model:** `text-embedding-3-small` (OpenAI) — cost-effective for code
- **Vector store:** Chroma (local, persistent) — one collection per repository
- **Retriever:** `VectorStoreRetriever` with `k=8`, `similarity_threshold=0.3`

### Index Lifecycle

| Trigger                                        | Action                                                 |
|------------------------------------------------|--------------------------------------------------------|
| First job on a repository                      | Full index build (clones repo, chunks, embeds, stores) |
| Repository updated (webhook or manual trigger) | Incremental re-index of changed files only             |
| Index older than 24 hours on an active repo    | Background refresh triggered before next job           |

### Limitations (v1.0)

- Maximum repository size: 500MB
- Supported languages: Python, JavaScript, TypeScript, Go, Java
- Binary files, generated code, and `node_modules` are excluded from indexing

---

## Agent Configuration

Users can configure each agent via the Settings page (Zone 1 header → Settings → Agents):

| Setting                | Options                                                  | Default            |
|------------------------|----------------------------------------------------------|--------------------|
| LLM Provider           | OpenAI, Anthropic                                        | OpenAI             |
| Model (per agent)      | gpt-4o-mini, gpt-4o, claude-3-5-haiku, claude-3-5-sonnet | See per-agent spec |
| LangServe Endpoint URL | Any valid URL                                            | localhost defaults |
| Model Gateway URL      | Any valid internal URL                                   | `http://litellm:4000` |
| System Prompt          | Free text (advanced)                                     | Built-in default   |
| Max Tokens             | 500–4000                                                 | 1500               |
| Temperature            | 0.0–0.5                                                  | 0.0                |

Configuration is stored per-repository in the backend database. Changes take effect on the next job submission.

---

## Inter-Agent Contract

All agents share a common interface contract to ensure the LangGraph supervisor can treat them uniformly.

### HTTP Contract (LangServe)

Every LangServe endpoint must accept:

- `POST /agents/{name}/invoke` with JSON body `{ "input": { ...AgentInput fields } }`
- Return `{ "output": { ...AgentFinding fields } }`

### AgentFinding Base Fields

Every agent output must include these base fields regardless of agent-specific fields:

```python
class AgentFindingBase(BaseModel):
    agent_name: str
    summary: str
    confidence: float  # 0.0–1.0
    reasoning: str
    error: str | None
```

The supervisor reads `confidence` and `error` to decide whether to accept the finding, retry, or escalate to human
input.
