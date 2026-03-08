---
id: PRD-004-1
title: Full LCEL Chain Specs — All Five Agents
status: DRAFT
domain: backend/agents
depends_on: [PRD-003, PRD-004]
key_decisions: [lcel-chain-pattern, tool-calling-pattern, agent-finding-translation, retry-fallback-composition]
---

# PRD-004-1 — Full LCEL Chain Specs: All Five Agents

| Field        | Value                                                                         |
|--------------|-------------------------------------------------------------------------------|
| Document ID  | PRD-004-1                                                                     |
| Version      | 1.0                                                                           |
| Status       | DRAFT                                                                         |
| Date         | March 2026                                                                    |
| Parent Doc   | [PRD-004](PRD-004-agent-layer.md)                                             |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md) (Orchestration)                 |

---

## 1. Purpose & Scope

This document provides complete, buildable LCEL chain specifications for all five agents. It exists because
PRD-004 leaves five implementation gaps that make the agents impossible to build directly from:

1. `tool_executor` in the Web Search agent chain is never defined — this doc provides the correct
   AIMessage → ToolMessage two-step pattern.
2. `merge_outputs_lambda` in the Writer agent is undefined — this doc provides the full merge function
   with all `WriterOutput` fields mapped.
3. `AgentFindingBase` (PRD-004) and `AgentFinding` (PRD-003) have incompatible fields — this doc
   provides a side-by-side comparison and a `_to_agent_finding()` translation helper.
4. `.with_retry()` + `.with_fallbacks()` composition order is never shown — this doc provides the
   canonical pattern.
5. The standard pattern in PRD-004 uses `PydanticOutputParser` — this doc replaces it with
   `with_structured_output()`, which is what all actual agents use.

**Boundary with PRD-004:** PRD-004 covers architecture decisions, service registry, LangServe setup,
LangFlow workflow, agent I/O schemas, and the Codebase Vector Index overview. This document covers
*only* the detailed internal chain implementations. Do not duplicate architecture decisions here.

**Boundary with PRD-004-2:** Retriever instantiation (`get_codebase_retriever`) is fully specified in
[PRD-004-2](PRD-004-2-codebase-index.md). This doc imports it.

---

## 2. Corrected Standard Pattern

PRD-004 shows `PydanticOutputParser` in the standard chain pattern. This is incorrect — all five agents
use `with_structured_output()` instead. The corrected pattern:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

prompt = ChatPromptTemplate.from_messages([
    ("system", AGENT_SYSTEM_PROMPT),
    ("human", AGENT_HUMAN_TEMPLATE),
])

llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    base_url=settings.model_gateway_url,  # e.g. http://litellm:4000
    api_key=settings.service_token,       # internal token, not the OpenAI key
)

chain = prompt | llm.with_structured_output(AgentOutputSchema)
```

`with_structured_output()` uses the model's native function-calling / JSON mode to enforce the schema.
`PydanticOutputParser` requires explicit format instructions in the prompt and is fragile with complex
nested schemas. Do not use `PydanticOutputParser` anywhere in this project.

### Retry + Fallback Composition

Every production chain wraps the core chain with retry and fallback:

```python
from langchain_core.runnables import RunnableWithFallbacks
from openai import RateLimitError

primary_chain = prompt | llm.with_structured_output(Schema)

fallback_llm = ChatOpenAI(
    model="gpt-4o-mini",   # cheaper fallback when primary (gpt-4o) is rate-limited
    temperature=0,
    base_url=settings.model_gateway_url,
    api_key=settings.service_token,
)
fallback_chain = prompt | fallback_llm.with_structured_output(Schema)

chain = primary_chain.with_retry(
    stop_after_attempt=3,
    retry_if_exception_type=(RateLimitError,),  # only retry on 429, not validation errors
).with_fallbacks([fallback_chain])
```

**Composition rule:** `.with_retry()` wraps the primary chain first. After all retries are exhausted on
the primary, `.with_fallbacks()` activates. The fallback itself does not retry — it runs once.

**What to retry:** Only `RateLimitError` (HTTP 429). Validation errors (`ValidationError`,
`OutputParserException`) indicate a schema mismatch that retrying will not fix — raise immediately.

**Fallback model:** GPT-4o-mini replaces GPT-4o. Same prompt template, same output schema, different
model. The fallback is not a degraded path — it produces valid output.

---

## 3. `AgentFindingBase` → `AgentFinding` Translation

### Schema Comparison

PRD-003 defines `AgentFinding` (the LangGraph state model). PRD-004 defines `AgentFindingBase` (the
common base for all agent outputs). These are different models with incompatible fields:

| Field              | `AgentFinding` (PRD-003, state) | `AgentFindingBase` (PRD-004, agent output) |
|--------------------|---------------------------------|--------------------------------------------|
| `agent_name`       | `str`                           | `str`                                      |
| `summary`          | `str`                           | `str`                                      |
| `confidence`       | `float`                         | `float`                                    |
| `details`          | `str`                           | *(absent)*                                 |
| `relevant_files`   | `list[str]`                     | *(absent)*                                 |
| `reasoning`        | *(absent)*                      | `str`                                      |
| `error`            | *(absent)*                      | `str \| None`                              |

Agent-specific subclasses of `AgentFindingBase` carry additional fields that supply the missing values:

| Agent subclass          | Field used for `details`   | Field used for `relevant_files`             |
|-------------------------|----------------------------|---------------------------------------------|
| `InvestigatorFinding`   | `hypothesis`               | `affected_areas` (list of area names)       |
| `CodebaseFinding`       | `root_cause_location`      | `[f.path for f in relevant_files]`          |
| `WebSearchFinding`      | `external_root_cause`      | `[r.url for r in relevant_results]`         |
| `CritiqueFinding`       | `revised_hypothesis`       | `gaps` (list of gap descriptions)           |
| `WriterOutput`          | `summary`                  | `[]` (writer does not reference files)      |

### Translation Helper

```python
from pydantic import BaseModel
from .models import AgentFinding, AgentFindingBase


def _to_agent_finding(
    raw: AgentFindingBase,
    details: str,
    relevant_files: list[str],
) -> AgentFinding:
    """
    Translate an AgentFindingBase (from a LangServe response) into the
    AgentFinding that the LangGraph state expects.

    Args:
        raw: The deserialized AgentFindingBase (or subclass) from the agent.
        details: Agent-specific text describing the finding in detail.
            Sourced from the most descriptive field of the subclass
            (e.g. InvestigatorFinding.hypothesis).
        relevant_files: List of file paths or URL strings associated with
            this finding. Empty list if the agent does not reference files.

    Returns:
        AgentFinding ready for appending to BugTriageState.findings.
    """
    return AgentFinding(
        agent_name=raw.agent_name,
        summary=raw.summary,
        confidence=raw.confidence,
        details=details,
        relevant_files=relevant_files,
    )
```

### Error Field Handling in LangGraph Nodes

`AgentFindingBase.error` has no counterpart in `AgentFinding`. It is handled **before** translation:
if the agent sets `error` to a non-None value, the LangGraph node logs the error and returns early
without appending a finding. The supervisor then re-routes based on the unchanged findings list.

Full node pattern (see Section 10 for complete call pattern):

```python
output = response.json()["output"]

if output.get("error"):
    logger.warning("agent=%s error=%s", node_name, output["error"])
    return {
        "current_node": node_name,
        "iterations": state["iterations"] + 1,
        # findings NOT appended — supervisor sees no new finding and may retry or escalate
    }

raw = AgentFindingBase(**output)
finding = _to_agent_finding(raw, details=..., relevant_files=...)
return {
    "findings": [finding],
    "current_node": node_name,
    "iterations": state["iterations"] + 1,
}
```

---

## 4. Investigator Agent

**Purpose:** Reads the full GitHub issue and forms an initial hypothesis about the bug.

### Prompt Template

```python
INVESTIGATOR_SYSTEM_PROMPT = """\
You are an expert software debugger. Your job is to read a GitHub issue report and form an initial,
structured hypothesis about the bug.

Guidelines:
- Be precise about affected areas: name modules, classes, or subsystems, not vague layers.
- Extract every error message or stack trace verbatim — these are the most valuable signals.
- Keywords should be search-ready: short, specific, likely to appear in source code or Stack Overflow.
- Confidence should reflect how clearly the issue body points to a root cause. Ambiguous issue = low confidence.
"""

INVESTIGATOR_HUMAN_TEMPLATE = """\
## GitHub Issue

Title: {issue_title}

Body:
{issue_body}

## Prior Findings
{prior_findings}

Analyze this issue and return a structured hypothesis.
"""

investigator_prompt = ChatPromptTemplate.from_messages([
    ("system", INVESTIGATOR_SYSTEM_PROMPT),
    ("human", INVESTIGATOR_HUMAN_TEMPLATE),
])
```

### Input / Output Models

```python
class InvestigatorInput(BaseModel):
    issue_title: str
    issue_body: str
    prior_findings: list[dict] = []


class InvestigatorFinding(AgentFindingBase):
    hypothesis: str                    # Concise root-cause hypothesis
    affected_areas: list[str]          # Module / subsystem names
    keywords_for_search: list[str]     # For Codebase Search and Web Search agents
    error_messages: list[str]          # Verbatim error strings from the issue body
```

### LCEL Chain

```python
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, ...)  # cheaper model: extraction-only task, no reasoning required

primary = investigator_prompt | llm.with_structured_output(InvestigatorFinding)
fallback = investigator_prompt | fallback_llm.with_structured_output(InvestigatorFinding)

chain = primary.with_retry(
    stop_after_attempt=3,
    retry_if_exception_type=(RateLimitError,),
).with_fallbacks([fallback])
```

### Node-Level Translation

```python
details = raw.hypothesis
relevant_files = raw.affected_areas  # area names used as "relevant files" proxy
```

---

## 5. Web Search Agent

### Why `bind_tools` Alone Is Not Enough

`llm.bind_tools([tavily])` tells the LLM about the tool and allows it to *request* a tool call. But
calling `.invoke()` on such a chain returns an `AIMessage` — not the tool results. The LLM's tool
call request is embedded in `AIMessage.tool_calls`. The pipe cannot continue until the tool is
*actually executed* and its output is fed back to the LLM as a `ToolMessage`.

Without explicit tool execution, `tool_executor` is undefined — the chain breaks here:

```python
# BROKEN — tool_executor is never defined; AIMessage cannot be piped directly to a prompt
chain = web_search_prompt | llm.bind_tools([tavily]) | tool_executor | web_result_prompt | ...
```

### ToolNode Pattern (Canonical)

Replace the custom `RunnableLambda` executor with `ToolNode` from `langgraph.prebuilt`. This
is required for `on_tool_start` / `on_tool_end` events to fire in `astream_events` v2, which
the frontend's Live Workspace tool call display depends on (see PRD-003-1 §Event Pipeline).

```python
# agentops/agents/web_search.py
from langchain_tavily import TavilySearch
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode

from agentops.models import AgentFinding, WebSearchState

# Tool definition — official Tavily package (pip install langchain-tavily)
_tavily = TavilySearch(max_results=5, search_depth="advanced")

# LLM with tool bound — produces AIMessage with tool_calls when search is needed
_llm_with_tools = ChatOpenAI(model="gpt-4o-mini", temperature=0).bind_tools([_tavily])

# Tool executor node — dispatches tool_calls, emits on_tool_start/on_tool_end
_tool_node = ToolNode(
    tools=[_tavily],
    handle_tool_errors=True,   # returns ToolMessage with error str instead of crashing
)

# Final structured output LLM — separate from tool-calling LLM (cannot chain reliably)
_structured_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
    AgentFinding
)


async def web_search_agent_node(state: WebSearchState) -> dict:
    """Web Search agent: calls Tavily, then formats result as AgentFinding."""
    # Step 1: LLM decides what to search for
    ai_msg = await _llm_with_tools.ainvoke(state["messages"])
    # Step 2: ToolNode executes the Tavily call(s) — emits on_tool_start/on_tool_end
    tool_result = await _tool_node.ainvoke({"messages": state["messages"] + [ai_msg]})
    # Step 3: Separate structured output LLM synthesizes findings
    finding = await _structured_llm.ainvoke(
        state["messages"] + [ai_msg] + tool_result["messages"]
    )
    return {"agent_findings": [finding]}
```

> **`langchain_tavily` vs deprecated community import:**
> `langchain_tavily` is the official Tavily package (`pip install langchain-tavily`).
> `langchain_community.tools.tavily_search.TavilySearchResults` is deprecated and will be
> removed in a future release. Constructor parameters are identical; `search_depth` accepts
> `"basic"` | `"advanced"` | `"fast"`.

> **Why separate LLMs for tool-calling and structured output?**
> `llm.bind_tools([tool]).with_structured_output(Schema)` cannot be reliably chained — the
> model sees multiple competing function schemas and conflates tool argument fields with output
> schema fields. Use two separate LLM calls: one with `bind_tools` for the search decision,
> one with `with_structured_output` for synthesis. The cost is one additional LLM call;
> the benefit is deterministic structured output.

> **Why `ToolNode` instead of `RunnableLambda`?**
> `ToolNode` from `langgraph.prebuilt` is the only pattern that emits `on_tool_start` /
> `on_tool_end` events through `astream_events` v2. A custom `RunnableLambda` emits only
> `on_chain_start` / `on_chain_end`. The frontend's Live Workspace tool call display
> (PRD-002) depends on `on_tool_start` events. `handle_tool_errors=True` returns a
> `ToolMessage` with the error string instead of crashing the graph when Tavily fails.

### Prompt Templates

The system prompts below structure `state["messages"]` before the node is called. The
tool-calling LLM sees `WEB_SEARCH_SYSTEM_PROMPT`; after tool results are appended the
structured output LLM sees the full history including `WEB_RESULT_SYSTEM_PROMPT`:

```python
WEB_SEARCH_SYSTEM_PROMPT = """\
You are a web research assistant specializing in software bugs. Given an issue report,
formulate precise web search queries to find:
1. Known bugs in the libraries or frameworks mentioned
2. Stack Overflow threads matching the exact error messages
3. GitHub issues in relevant repositories
Use the tavily_search tool to execute your searches.
"""

WEB_RESULT_SYSTEM_PROMPT = """\
You are a software bug analyst. Review the web search results below and synthesize findings
relevant to the bug described. Identify external root causes, known issues, or relevant
documentation. Return structured output only.
"""
```

### Node-Level Translation

```python
details = raw.external_root_cause or "No external root cause identified."
relevant_files = [r.url for r in raw.relevant_results]
```

---

## 6. Codebase Search Agent

### Retriever Import

`get_codebase_retriever` is defined and fully specified in
[PRD-004-2](PRD-004-2-codebase-index.md#5-codebase_retriever-instantiation). Import it:

```python
from agentops_codebase_index.retriever import get_codebase_retriever
```

It accepts a `repository` URL string and returns a `VectorStoreRetriever` for the correct Chroma
collection.

### Prompt Template

```python
CODEBASE_SEARCH_SYSTEM_PROMPT = """\
You are a code analysis expert. You have been given relevant code snippets retrieved from
the repository via semantic search. Your task is to identify which files and code paths are
most likely involved in the reported bug, and to pinpoint the root cause location if possible.

Be specific: name exact file paths, function names, and line regions where possible.
"""

codebase_search_prompt = ChatPromptTemplate.from_messages([
    ("system", CODEBASE_SEARCH_SYSTEM_PROMPT),
    ("human", (
        "Hypothesis: {hypothesis}\n\n"
        "Keywords: {keywords}\n\n"
        "Retrieved code context:\n{context}"
    )),
])
```

### Input / Output Models

```python
class CodebaseSearchInput(BaseModel):
    repository: str
    keywords: list[str]
    hypothesis: str
    affected_areas: list[str]


class RelevantFile(BaseModel):
    path: str
    relevance_reason: str


class CodebaseFinding(AgentFindingBase):
    relevant_files: list[RelevantFile]
    root_cause_location: str | None
```

### LCEL Chain

The `RunnableParallel` passes the issue context alongside the retrieved code snippets. The retriever
is instantiated at call time using the `repository` field from the input:

```python
from langchain_core.runnables import RunnableParallel, RunnablePassthrough, RunnableLambda
from langchain_core.vectorstores import VectorStoreRetriever


def build_codebase_chain(retriever: VectorStoreRetriever):
    """Build the RAG chain for a pre-built repository retriever."""
    primary = (
        RunnableParallel({
            "context": (lambda x: " ".join(x["keywords"])) | retriever,
            "hypothesis": RunnablePassthrough() | (lambda x: x["hypothesis"]),
            "keywords": RunnablePassthrough() | (lambda x: ", ".join(x["keywords"])),
        })
        | codebase_search_prompt
        | llm.with_structured_output(CodebaseFinding)
    )
    fallback = (
        RunnableParallel({
            "context": (lambda x: " ".join(x["keywords"])) | retriever,
            "hypothesis": RunnablePassthrough() | (lambda x: x["hypothesis"]),
            "keywords": RunnablePassthrough() | (lambda x: ", ".join(x["keywords"])),
        })
        | codebase_search_prompt
        | fallback_llm.with_structured_output(CodebaseFinding)
    )
    return primary.with_retry(
        stop_after_attempt=3,
        retry_if_exception_type=(RateLimitError,),
    ).with_fallbacks([fallback])
```

The caller (`codebase_search_node` in PRD-004-2 §5) calls `get_codebase_retriever(state["repository"])`
first, then passes the retriever into `build_codebase_chain(retriever)`. This keeps collection
validation (and its exception) outside the chain itself.

### Node-Level Translation

```python
details = raw.root_cause_location or "Root cause location not identified."
relevant_files = [f.path for f in raw.relevant_files]
```

---

## 7. Critic Agent

**Purpose:** Challenges the accumulated findings adversarially. Flags gaps, adjusts confidence, and
decides whether the triage is complete enough to send to the Writer.

### Prompt Template

```python
CRITIC_SYSTEM_PROMPT = """\
You are an adversarial code review expert. Your job is to challenge the findings produced by
other agents and identify weaknesses, gaps, or overconfident conclusions.

Evaluation rubric:
- CONFIRMED: The findings are coherent, well-evidenced, and sufficient to write a triage report.
- UNCERTAIN: The findings are plausible but lack direct code evidence or have unresolved contradictions.
- CHALLENGED: The findings are speculative, contradictory, or missing key evidence. More investigation needed.

Be strict. A finding is only CONFIRMED if you would be comfortable filing a bug ticket based on it.
"""

CRITIC_HUMAN_TEMPLATE = """\
## Current Hypothesis
{current_hypothesis}

## All Findings So Far
{all_findings}

## Codebase Evidence
{codebase_evidence}

Review the above and return your verdict.
"""

critic_prompt = ChatPromptTemplate.from_messages([
    ("system", CRITIC_SYSTEM_PROMPT),
    ("human", CRITIC_HUMAN_TEMPLATE),
])
```

### Input / Output Models

```python
class CriticInput(BaseModel):
    all_findings: list[dict]
    current_hypothesis: str
    codebase_evidence: list[str]


class CriticVerdict(BaseModel):
    verdict: Literal["APPROVED", "REJECTED"]
    """Binary gate: APPROVED means writer may proceed; REJECTED means re-investigation needed."""

    gaps: list[str] = Field(default_factory=list)
    """Specific gaps or unsupported claims. Empty list when verdict is APPROVED."""

    required_evidence: list[str] = Field(default_factory=list)
    """What additional evidence would change verdict to APPROVED. Empty when APPROVED."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Critic's confidence in the verdict (0.0–1.0)."""


class CritiqueFinding(AgentFindingBase):
    verdict: Literal["CONFIRMED", "UNCERTAIN", "CHALLENGED"]
    confidence_adjustment: float   # delta applied to overall confidence
    gaps: list[str]                # specific gaps identified
    revised_hypothesis: str | None
    ready_for_report: bool         # True only if verdict == CONFIRMED
```

`CriticVerdict` is the binary gate used by the supervisor for routing decisions. It is stored in
`BugTriageState.critic_feedback`. `CritiqueFinding` (stored in `findings`) carries the full
adversarial review detail for tracing and report purposes.

### LCEL Chain

```python
primary = critic_prompt | llm.with_structured_output(CritiqueFinding)
fallback = critic_prompt | fallback_llm.with_structured_output(CritiqueFinding)

chain = primary.with_retry(
    stop_after_attempt=3,
    retry_if_exception_type=(RateLimitError,),
).with_fallbacks([fallback])
```

### Node-Level Translation

```python
details = raw.revised_hypothesis or f"Verdict: {raw.verdict}. Gaps: {'; '.join(raw.gaps)}"
relevant_files = raw.gaps  # gaps used as "relevant files" — they are next investigation targets
```

---

## 8. Writer Agent

**Purpose:** Produces the final triage report, GitHub comment draft, and ticket fields from all
accumulated findings.

### Sub-Chain Specifications

The Writer chain uses `RunnableParallel` to generate three outputs simultaneously:

#### `report_chain` → `TriageReport`

```python
REPORT_SYSTEM_PROMPT = """\
You are a technical writer producing a structured bug triage report. Based on all agent findings,
produce a concise, factual report. Severity levels: CRITICAL, HIGH, MEDIUM, LOW.
"""

REPORT_HUMAN_TEMPLATE = """\
Issue: {issue_title} ({issue_url})
Repository: {repository}

All Findings:
{all_findings}

Human Exchanges:
{human_exchanges}

Produce the triage report.
"""

report_prompt = ChatPromptTemplate.from_messages([
    ("system", REPORT_SYSTEM_PROMPT),
    ("human", REPORT_HUMAN_TEMPLATE),
])

report_chain = report_prompt | llm.with_structured_output(TriageReport)
```

#### `comment_chain` → `str` (GitHub markdown)

```python
COMMENT_SYSTEM_PROMPT = """\
You are writing a GitHub issue comment on behalf of an automated triage system. The tone should
be professional, concise, and helpful. Include: root cause summary, affected files, next steps.
Format with markdown headings and code blocks where appropriate.
"""

comment_prompt = ChatPromptTemplate.from_messages([
    ("system", COMMENT_SYSTEM_PROMPT),
    ("human", (
        "Issue: {issue_title}\n"
        "Repository: {repository}\n"
        "Findings summary: {all_findings}\n\n"
        "Write the GitHub comment."
    )),
])

# StrOutputParser returns a plain string, which is what we want for markdown
from langchain_core.output_parsers import StrOutputParser
comment_chain = comment_prompt | llm | StrOutputParser()
```

#### `ticket_chain` → `dict` (raw JSON)

```python
TICKET_SYSTEM_PROMPT = """\
You are extracting ticket metadata from a bug triage. Return JSON with these fields:
- title: concise bug ticket title (string)
- labels: list of GitHub label strings (e.g. ["bug", "backend", "high-priority"])
- assignee: GitHub username of the most likely owner (string or null)
- effort: effort estimate as XS, S, M, L, or XL (string)
"""

ticket_prompt = ChatPromptTemplate.from_messages([
    ("system", TICKET_SYSTEM_PROMPT),
    ("human", (
        "Issue: {issue_title}\n"
        "Repository: {repository}\n"
        "Findings: {all_findings}\n\n"
        "Return the ticket metadata JSON."
    )),
])

# JSON mode — model returns a raw dict; no Pydantic schema needed here
ticket_llm = ChatOpenAI(model="gpt-4o", temperature=0, ...).bind(
    response_format={"type": "json_object"}
)
import json
from langchain_core.output_parsers import StrOutputParser
ticket_chain = ticket_prompt | ticket_llm | StrOutputParser() | json.loads
```

### `merge_writer_outputs` — Fully Specified

```python
from langchain_core.runnables import RunnableLambda, RunnableParallel


def merge_writer_outputs(parallel_output: dict) -> WriterOutput:
    """
    Merge the three parallel sub-chain outputs into a single WriterOutput.

    parallel_output keys:
        "report"  → TriageReport (from report_chain)
        "comment" → str          (from comment_chain, GitHub markdown)
        "ticket"  → dict         (from ticket_chain, raw JSON fields)
    """
    report: TriageReport = parallel_output["report"]
    ticket: dict = parallel_output["ticket"]

    return WriterOutput(
        agent_name="writer",
        summary=f"Triage complete: {report.severity} severity",
        confidence=report.confidence,
        reasoning="Final report generated from accumulated findings.",
        error=None,
        report=report,
        github_comment_markdown=parallel_output["comment"],
        ticket_title=ticket["title"],
        ticket_labels=ticket["labels"],
        ticket_assignee_suggestion=ticket.get("assignee") or "",
        ticket_effort_estimate=ticket.get("effort", "M"),
    )


chain = (
    RunnableParallel({
        "report": report_chain,
        "comment": comment_chain,
        "ticket": ticket_chain,
    })
    | RunnableLambda(merge_writer_outputs)
)
```

**Field mapping notes:**
- `report.confidence` becomes `WriterOutput.confidence` — the report's confidence is the final
  system confidence.
- `ticket.get("assignee") or ""` normalises `null` from the LLM JSON to an empty string.
- `ticket.get("effort", "M")` defaults to "M" if the LLM omits the field.
- `WriterOutput` extends `AgentFindingBase`; the `reasoning` field is set to a static summary
  string rather than left empty.

### LCEL Chain (Full)

```python
primary_chain = (
    RunnableParallel({
        "report": report_chain,
        "comment": comment_chain,
        "ticket": ticket_chain,
    })
    | RunnableLambda(merge_writer_outputs)
)

# Fallback uses same structure with fallback LLMs in each sub-chain
fallback_report_chain = report_prompt | fallback_llm.with_structured_output(TriageReport)
fallback_comment_chain = comment_prompt | fallback_llm | StrOutputParser()
fallback_ticket_chain = ticket_prompt | fallback_ticket_llm | StrOutputParser() | json.loads

fallback_chain = (
    RunnableParallel({
        "report": fallback_report_chain,
        "comment": fallback_comment_chain,
        "ticket": fallback_ticket_chain,
    })
    | RunnableLambda(merge_writer_outputs)
)

chain = primary_chain.with_retry(
    stop_after_attempt=3,
    retry_if_exception_type=(RateLimitError,),
).with_fallbacks([fallback_chain])
```

---

## 9. `.with_retry()` + `.with_fallbacks()` Composition Reference

This section consolidates the rules from the individual agents above.

### Canonical Pattern

```python
chain = primary_chain.with_retry(
    stop_after_attempt=3,
    retry_if_exception_type=(RateLimitError,),
).with_fallbacks([fallback_chain])
```

### Execution Sequence

```
Attempt 1: primary_chain
    → RateLimitError → wait (exponential backoff, managed by with_retry)
Attempt 2: primary_chain
    → RateLimitError → wait
Attempt 3: primary_chain
    → RateLimitError → with_retry exhausted → with_fallbacks activates
Attempt 4: fallback_chain (runs once, no retry on fallback)
    → success → return output
    → exception → propagated to caller (node sets error field)
```

### Rules

| Rule | Detail |
|------|--------|
| Retry only on 429 | `retry_if_exception_type=(RateLimitError,)` — validation errors are not retried |
| Max 3 attempts | `stop_after_attempt=3` — primary tries once + two retries |
| Fallback model | GPT-4o-mini replaces GPT-4o; same prompt + schema |
| Fallback runs once | No `.with_retry()` on the fallback chain |
| Wrap before fallback | `.with_retry()` must be called before `.with_fallbacks()` |

---

## 10. LangServe Call Pattern from LangGraph Nodes

LangGraph nodes call LangServe over HTTP using `httpx` (as specified in PRD-003). After receiving
the response, the node translates the output to `AgentFinding` using `_to_agent_finding()`.

### Full Node Pattern

```python
import httpx
import logging
from .translation import _to_agent_finding

logger = logging.getLogger(__name__)


async def investigator_node(state: BugTriageState) -> dict:
    node_name = "investigator"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.investigator_url}/agents/investigator/invoke",
            json={
                "input": {
                    "issue_title": state["issue_title"],
                    "issue_body": state["issue_body"],
                    "prior_findings": state["findings"],
                }
            },
            timeout=60.0,
        )
    response.raise_for_status()

    output: dict = response.json()["output"]

    # Error field check: if the agent set error, do not append a finding
    if output.get("error"):
        logger.warning("agent=%s error=%s", node_name, output["error"])
        return {
            "current_node": node_name,
            "iterations": state["iterations"] + 1,
            # findings NOT appended — supervisor sees no new finding and may retry or escalate
        }

    raw = InvestigatorFinding(**output)

    finding = _to_agent_finding(
        raw=raw,
        details=raw.hypothesis,
        relevant_files=raw.affected_areas,
    )

    return {
        "findings": [finding],
        "current_node": node_name,
        "iterations": state["iterations"] + 1,
    }
```

### `response.json()["output"]` Structure

LangServe wraps the chain's return value in an `output` key:

```json
{
  "output": {
    "agent_name": "investigator",
    "summary": "JWT token expiry check uses server-local time instead of UTC",
    "confidence": 0.75,
    "reasoning": "The issue body clearly describes a timezone-related token expiry bug.",
    "error": null,
    "hypothesis": "...",
    "affected_areas": ["auth", "token_validator"],
    "keywords_for_search": ["jwt", "expiry", "utc", "timezone"],
    "error_messages": ["TokenExpiredError: token has expired"]
  }
}
```

The `output` dict is deserialized directly into the agent-specific Pydantic model (e.g.
`InvestigatorFinding(**output)`). Translation to `AgentFinding` happens after this step.
