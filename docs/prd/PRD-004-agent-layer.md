# PRD-004 — Agent Layer: LangChain, LCEL, LangServe & LangFlow

## AgentOps Dashboard — Individual Agent Requirements

| Field        | Value                                            |
|--------------|--------------------------------------------------|
| Document ID  | PRD-004                                          |
| Version      | 1.0                                              |
| Status       | DRAFT                                            |
| Date         | March 2026                                       |
| Parent Doc   | PRD-001                                          |
| Related Docs | PRD-003 (Orchestration), PRD-005 (Observability) |

---

## Table of Contents

1. [Overview](#1-overview)
2. [LangChain + LCEL — Agent Internals](#2-langchain--lcel--agent-internals)
3. [LangServe — Agent Microservices](#3-langserve--agent-microservices)
4. [LangFlow — Prototyping Workflow](#4-langflow--prototyping-workflow)
5. [Agent Specifications](#5-agent-specifications)
    - [5.1 Investigator Agent](#51-investigator-agent)
    - [5.2 Codebase Search Agent](#52-codebase-search-agent)
    - [5.3 Web Search Agent](#53-web-search-agent)
    - [5.4 Critic Agent](#54-critic-agent)
    - [5.5 Writer Agent](#55-writer-agent)
6. [Codebase Vector Index](#6-codebase-vector-index)
7. [Agent Configuration](#7-agent-configuration)
8. [Inter-Agent Contract](#8-inter-agent-contract)

---

## 1. Overview

This document covers the **individual agent layer** — the internals of each of the five specialized worker agents. These
agents are the leaves of the system: the LangGraph supervisor (PRD-003) calls them, but doesn't know or care what's
inside.

Each agent follows the same lifecycle:

1. **Designed and tested visually in LangFlow** (prototyping)
2. **Implemented as an LCEL chain** in Python using LangChain primitives
3. **Deployed as a LangServe endpoint** — an independent HTTP microservice
4. **Called by the LangGraph supervisor** via HTTP during job execution

This separation is intentional. Agents are independently swappable, versioned, and testable without touching the
orchestration layer.

---

## 2. LangChain + LCEL — Agent Internals

### 2.1 Why LCEL

Every agent's core logic is an LCEL (LangChain Expression Language) chain. LCEL is chosen over the legacy `LLMChain`
approach because:

- **Streaming by default** — every LCEL chain supports `astream()`, which LangServe exposes automatically
- **Async by default** — critical for running multiple agents concurrently
- **Composable** — complex agents (like Codebase Search with RAG) can be built by piping components cleanly
- **LangSmith integration** — LCEL chains are automatically traced without any additional instrumentation code
- **Parallel execution** — `RunnableParallel` lets agents fetch context from multiple sources simultaneously

### 2.2 Standard LCEL Chain Pattern

Every agent in this system follows this base pattern:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI

# 1. Prompt template
prompt = ChatPromptTemplate.from_messages([
    ("system", AGENT_SYSTEM_PROMPT),
    ("human", AGENT_HUMAN_TEMPLATE),
])

# 2. LLM (swappable — see Agent Configuration section)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 3. Output parser — all agents return structured Pydantic models
parser = PydanticOutputParser(pydantic_object=AgentFinding)

# 4. Chain — the pipe operator is LCEL
chain = prompt | llm | parser
```

The `chain` object is what gets served via LangServe.

### 2.3 LCEL Features Used Per Agent

| Feature               | Agents          | Purpose                                                      |
|-----------------------|-----------------|--------------------------------------------------------------|
| `RunnableParallel`    | Codebase Search | Fetches vector store results and issue body simultaneously   |
| `RunnablePassthrough` | All             | Passes through input fields that the prompt needs unchanged  |
| `RunnableLambda`      | Writer          | Custom post-processing to format the GitHub comment markdown |
| `.with_retry()`       | All             | Automatic retry on LLM rate limits (max 3 attempts)          |
| `.with_fallbacks()`   | All             | Falls back from GPT-4o to GPT-4o-mini on repeated failures   |
| `.astream()`          | All             | Enables token-by-token streaming through LangServe           |

---

## 3. LangServe — Agent Microservices

### 3.1 Architecture Decision

Rather than importing agent functions directly into the LangGraph process, each agent is deployed as a **standalone
FastAPI + LangServe microservice**. The LangGraph nodes call these services over HTTP.

Benefits:

- Each agent is independently deployable and restartable
- Agent prompts, models, and logic can be updated without redeploying the orchestration layer
- Horizontal scaling: a heavy agent (like Codebase Search) can be scaled independently
- Clear ownership boundary: a team member can "own" one agent service
- The agent config UI (Zone 3 settings) just stores endpoint URLs — fully pluggable

### 3.2 Service Registry

| Service Name               | Default Port | Endpoint                  | Description                            |
|----------------------------|--------------|---------------------------|----------------------------------------|
| `agentops-investigator`    | 8001         | `/agents/investigator`    | Reads and interprets GitHub issues     |
| `agentops-codebase-search` | 8002         | `/agents/codebase-search` | Semantic search over repository code   |
| `agentops-web-search`      | 8003         | `/agents/web-search`      | Web search for errors and stack traces |
| `agentops-critic`          | 8004         | `/agents/critic`          | Reviews findings for correctness       |
| `agentops-writer`          | 8005         | `/agents/writer`          | Produces final structured report       |

### 3.3 LangServe Setup Pattern

Each service uses the same setup pattern:

```python
# agent_service/server.py
from fastapi import FastAPI
from langserve import add_routes
from .chain import chain  # the LCEL chain

app = FastAPI(title="AgentOps — Investigator Agent")

add_routes(
    app,
    chain,
    path="/agents/investigator",
    enable_feedback_endpoint=True,  # lets LangSmith capture feedback
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
```

LangServe automatically generates:

- `POST /agents/investigator/invoke` — single synchronous call
- `POST /agents/investigator/stream` — streaming response
- `POST /agents/investigator/batch` — batch processing
- `GET  /agents/investigator/playground` — interactive testing UI

### 3.4 LangServe Playground

Each LangServe endpoint comes with a built-in `/playground` UI at no extra cost. This is used during development to
manually test agent behavior with real GitHub issues before running full end-to-end jobs. This complements the LangFlow
prototyping workflow.

---

## 4. LangFlow — Prototyping Workflow

### 4.1 Role in Development Process

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

### 4.2 Agent Configuration UI

In v1.1, the Settings page of AgentOps Dashboard will embed LangFlow's canvas (via iframe or the LangFlow API). This
allows users to:

- Visually modify an agent's prompt, model, or chain structure
- Test the modified chain against a sample issue before saving
- Push the updated chain to the LangServe endpoint

This is the product's equivalent of a "plugin editor" — power users can customize agent behavior without writing code.

### 4.3 What Gets Prototyped in LangFlow

| Agent           | LangFlow Prototype Focus                                                               |
|-----------------|----------------------------------------------------------------------------------------|
| Investigator    | System prompt calibration — how structured should the hypothesis be?                   |
| Codebase Search | RAG retriever settings — chunk size, k, similarity threshold                           |
| Web Search      | Tavily query formulation — how to turn an issue into a good search query               |
| Critic          | Scoring rubric — what makes a finding "confident enough" vs "needs more investigation" |
| Writer          | Output format — structured report vs. free-form markdown; GitHub comment tone          |

---

## 5. Agent Specifications

### 5.1 Investigator Agent

**Purpose:** First agent to run. Reads the full GitHub issue body and forms an initial hypothesis about the bug's
nature, affected areas, and likely root cause.

**Input:**

```python
class InvestigatorInput(BaseModel):
    issue_title: str
    issue_body: str
    prior_findings: list[dict] = []  # empty on first call
```

**Output:**

```python
class InvestigatorFinding(BaseModel):
    hypothesis: str  # plain English statement of likely root cause
    affected_areas: list[str]  # e.g. ["authentication", "database"]
    keywords_for_search: list[str]  # passed to codebase/web search agents
    error_messages: list[str]  # extracted verbatim error strings
    confidence: float  # 0.0–1.0
    reasoning: str  # shown in UI agent card
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

### 5.2 Codebase Search Agent

**Purpose:** Searches the repository's source code for files and code snippets relevant to the bug. Uses semantic vector
search against a pre-built Chroma index of the repository.

**Input:**

```python
class CodebaseSearchInput(BaseModel):
    repository: str  # "org/repo"
    keywords: list[str]  # from Investigator's keywords_for_search
    hypothesis: str  # guides query formulation
    affected_areas: list[str]
```

**Output:**

```python
class CodebaseFinding(BaseModel):
    relevant_files: list[RelevantFile]  # filepath + relevant snippet + line numbers
    root_cause_location: Optional[str]  # "auth/middleware.py:L142" if found
    confidence: float
    reasoning: str
```

**LCEL Chain (with RAG):**

```python
# RunnableParallel fetches vector context and passes input simultaneously
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

### 5.3 Web Search Agent

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
class WebSearchFinding(BaseModel):
    relevant_results: list[WebResult]  # URL + title + relevant excerpt
    external_root_cause: Optional[str]  # e.g. "Known bug in requests v2.31"
    confidence: float
    reasoning: str
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

### 5.4 Critic Agent

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
class CritiqueFinding(BaseModel):
    verdict: Literal["CONFIRMED", "UNCERTAIN", "CHALLENGED"]
    confidence_adjustment: float  # delta to apply to current confidence
    gaps: list[str]  # what's still missing
    revised_hypothesis: Optional[str]
    ready_for_report: bool  # supervisor uses this to decide next step
    reasoning: str
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

### 5.5 Writer Agent

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
class WriterOutput(BaseModel):
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

## 6. Codebase Vector Index

### 6.1 Purpose

The Codebase Search Agent needs semantic search over the repository's source code. A keyword-based search is
insufficient for finding the code path related to "JWT token expiry on UTC server" when the actual code says
`if token.exp < time.time()`.

### 6.2 Implementation

```
Repository Clone → Code Chunking → Embedding → Chroma Vector Store
```

- **Chunking:** `RecursiveCharacterTextSplitter` with `chunk_size=1000`, `chunk_overlap=200`, splitting on Python/JS/TS
  syntax boundaries
- **Embedding model:** `text-embedding-3-small` (OpenAI) — cost-effective for code
- **Vector store:** Chroma (local, persistent) — one collection per repository
- **Retriever:** `VectorStoreRetriever` with `k=8`, `similarity_threshold=0.3`

### 6.3 Index Lifecycle

| Trigger                                        | Action                                                 |
|------------------------------------------------|--------------------------------------------------------|
| First job on a repository                      | Full index build (clones repo, chunks, embeds, stores) |
| Repository updated (webhook or manual trigger) | Incremental re-index of changed files only             |
| Index older than 24 hours on an active repo    | Background refresh triggered before next job           |

### 6.4 Limitations (v1.0)

- Maximum repository size: 500MB
- Supported languages: Python, JavaScript, TypeScript, Go, Java
- Binary files, generated code, and `node_modules` are excluded from indexing

---

## 7. Agent Configuration

Users can configure each agent via the Settings page (Zone 1 header → Settings → Agents):

| Setting                | Options                                                  | Default            |
|------------------------|----------------------------------------------------------|--------------------|
| LLM Provider           | OpenAI, Anthropic                                        | OpenAI             |
| Model (per agent)      | gpt-4o-mini, gpt-4o, claude-3-5-haiku, claude-3-5-sonnet | See per-agent spec |
| LangServe Endpoint URL | Any valid URL                                            | localhost defaults |
| System Prompt          | Free text (advanced)                                     | Built-in default   |
| Max Tokens             | 500–4000                                                 | 1500               |
| Temperature            | 0.0–0.5                                                  | 0.0                |

Configuration is stored per-repository in the backend database. Changes take effect on the next job submission.

---

## 8. Inter-Agent Contract

All agents share a common interface contract to ensure the LangGraph supervisor can treat them uniformly.

### 8.1 HTTP Contract (LangServe)

Every LangServe endpoint must accept:

- `POST /agents/{name}/invoke` with JSON body `{ "input": { ...AgentInput fields } }`
- Return `{ "output": { ...AgentFinding fields } }`

### 8.2 AgentFinding Base Fields

Every agent output must include these base fields regardless of agent-specific fields:

```python
class AgentFindingBase(BaseModel):
    agent_name: str  # matches node name in LangGraph
    summary: str  # 1–2 sentence summary for UI agent card
    confidence: float  # 0.0–1.0 — used by supervisor for routing decisions
    reasoning: str  # full reasoning shown in UI (streamed token by token)
    error: Optional[str]  # set if agent encountered an error internally
```

The supervisor reads `confidence` and `error` to decide whether to accept the finding, retry, or escalate to human
input.
