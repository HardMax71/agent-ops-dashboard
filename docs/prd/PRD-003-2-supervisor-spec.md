---
id: PRD-003-2
title: Supervisor Agent — Full Prompt & Routing Specification
status: DRAFT
domain: backend/orchestration
depends_on: [PRD-003]
---

# PRD-003-2 — Supervisor Agent: Full Prompt & Routing Specification

| Field        | Value                                                                         |
|--------------|-------------------------------------------------------------------------------|
| Document ID  | PRD-003-2                                                                     |
| Version      | 1.0                                                                           |
| Status       | DRAFT                                                                         |
| Date         | March 2026                                                                    |
| Parent Doc   | [PRD-003](PRD-003-langgraph-orchestration.md)                                 |

---

## 1. Purpose & Scope

This document makes the supervisor node fully implementable. PRD-003 §Supervisor Agent Design
contains an abbreviated system prompt and a partial `SupervisorDecision` schema. This document
provides:

- The complete system prompt with every agent description, routing rule, and threshold
- The full context serialisation format for all state fields passed to the prompt
- `SupervisorDecision` validation and error recovery logic
- Routing guards applied in code after the LLM call
- Confidence thresholds and their enforcement strategy
- Prompt versioning and in-flight job safety

**Boundary with PRD-003:** PRD-003 specifies the graph structure, state schema, HITL flow, and
the abbreviated supervisor design. This document is the complete implementation reference for
the supervisor node specifically.

---

## 2. Node Implementation

Exception handling for the LLM retry logic is isolated in `_invoke_supervisor()` — a single
`try/except` inside a loop (see PRD-007 §Architecture policy: no nested try-catches; retry
logic uses one try-except in a dedicated helper). `supervisor_node()` itself is exception-free.

```python
# nodes/supervisor.py

import logging
from pydantic import ValidationError
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .state import BugTriageState, HumanExchange, SupervisorDecision
from .prompts import build_supervisor_system_prompt, build_supervisor_context

logger = logging.getLogger(__name__)

_CORRECTION_PROMPT = (
    "Your previous response was invalid. Error: {error}\n"
    "Please respond again with valid JSON matching the schema exactly.\n"
    "The next_node field must be one of: investigator, codebase_search, "
    "web_search, critic, human_input, writer, end."
)

_FORCED_FALLBACK = SupervisorDecision(
    next_node="writer",
    reasoning="Forced to writer due to repeated supervisor output validation failure.",
    question=None,
    question_context=None,
    confidence=0.0,
)


async def _invoke_supervisor(
    structured_llm: object,
    base_messages: list[BaseMessage],
) -> SupervisorDecision:
    """Invoke the supervisor LLM with one correction retry on validation failure.

    Uses a single try/except inside a loop — the only place exception handling
    lives for supervisor invocation. Returns a forced fallback decision (route to
    writer) if both attempts fail rather than propagating the exception.
    """
    messages = base_messages
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            return await structured_llm.ainvoke(messages)
        except (ValidationError, Exception) as exc:
            last_error = exc
            if attempt == 0:
                logger.warning("Supervisor output invalid (attempt 1): %s", exc)
                messages = base_messages + [
                    HumanMessage(content=_CORRECTION_PROMPT.format(error=exc))
                ]

    logger.error("Supervisor output invalid (attempt 2): %s", last_error)
    return _FORCED_FALLBACK


async def supervisor_node(state: BugTriageState) -> dict:
    """Decide the next graph step from current triage state.

    Builds the supervisor prompt, invokes the LLM via _invoke_supervisor
    (which handles the one-retry recovery pattern), and translates the
    decision into state updates.
    """
    system_prompt = build_supervisor_system_prompt()
    context_message = build_supervisor_context(state)
    structured_llm = llm.with_structured_output(SupervisorDecision)

    decision = await _invoke_supervisor(
        structured_llm,
        [SystemMessage(content=system_prompt), HumanMessage(content=context_message)],
    )

    updates: dict = {
        "next_node": decision.next_node,
        "supervisor_reasoning": decision.reasoning,
    }

    if decision.next_node == "human_input":
        updates["pending_exchange"] = HumanExchange(
            question=decision.question or "",
            context=decision.question_context or "",
        )
        updates["awaiting_human"] = True

    return updates
```

---

## 3. Full System Prompt

```
You are the supervisor of a bug triage team. You coordinate specialised agents
to investigate a GitHub issue and produce a structured triage report.

## Your agents

- **investigator**: Reads and interprets the issue body and any attached
  stack traces or error messages. ALWAYS call this first — before any other agent.
  Input it receives: issue_title, issue_body, prior_findings.

- **codebase_search**: Searches the repository source code for the root cause.
  Call when you have a hypothesis about which code path is responsible and need
  to locate the exact file and line. Do not call more than twice per job unless
  explicitly redirected.

- **web_search**: Searches the web for context on error messages, library bugs,
  or framework behaviour. Call when the issue contains a cryptic error code or
  references a third-party library that codebase_search cannot help with.

- **critic**: Reviews the current set of findings for correctness, gaps, and
  contradictions. Call when you have a concrete hypothesis and want a second opinion
  before writing the final report. Calling critic more than once wastes iterations.

- **human_input**: Asks the user a clarifying question. Call ONLY IF:
  (a) Two or more equally plausible root causes remain after investigation and
      you cannot distinguish them without user knowledge (e.g. recent deployment
      changes, environment-specific configuration), OR
  (b) Critical context is missing that no tool can retrieve.
  Do NOT call if you can still run codebase_search or web_search to find the answer.
  Maximum 2 questions per job total. Frame questions with 2-3 concrete options when
  possible to reduce cognitive load.

- **writer**: Produces the final triage report, GitHub comment draft, and ticket
  draft. Call when you have sufficient evidence to explain the root cause with
  confidence >= 0.7 and at least 2 corroborating findings, OR confidence >= 0.85
  with a single high-quality finding, OR you have reached the iteration limit.

## Redirect instructions
{redirect_instructions_block}

## Current state
Iteration: {iterations} / {max_iterations}
Questions asked so far: {questions_asked} / 2

## Findings so far
{findings_block}

## Human exchanges so far
{human_exchanges_block}

## Your task
Decide the next step. Output JSON with these fields:
- next_node: one of "investigator", "codebase_search", "web_search", "critic",
  "human_input", "writer", "end"
- reasoning: your chain-of-thought for this decision (1-3 sentences)
- question: the question to ask the user (only when next_node == "human_input",
  otherwise null)
- question_context: additional context to show alongside the question (null otherwise)
- confidence: your confidence in the current root cause hypothesis (0.0-1.0).
  Use 0.0 if no hypothesis yet.
```

---

## 4. Context Serialisation Format

The `build_supervisor_context(state)` function produces the `HumanMessage` content by
interpolating the template variables in §3.

### `findings_block`

Each `AgentFinding` is serialised as:

```
[{n}] {agent_name} (confidence: {confidence:.0%})
Summary: {summary}
Details: {details}
Relevant files: {", ".join(relevant_files) or "none"}
```

Findings are separated by a blank line. If `state.findings` is empty:

```
No findings yet.
```

Implementation:

```python
def _format_findings(findings: list[AgentFinding]) -> str:
    if not findings:
        return "No findings yet."
    parts = []
    for n, f in enumerate(findings, 1):
        files = ", ".join(f.relevant_files) if f.relevant_files else "none"
        parts.append(
            f"[{n}] {f.agent_name} (confidence: {f.confidence:.0%})\n"
            f"Summary: {f.summary}\n"
            f"Details: {f.details}\n"
            f"Relevant files: {files}"
        )
    return "\n\n".join(parts)
```

### `human_exchanges_block`

Each `HumanExchange` is serialised as:

```
Q: {question}
Context: {context}
A: {answer or "(awaiting answer)"}
```

If `state.human_exchanges` is empty: `"None."`. If `state.pending_exchange` exists and has not
yet been answered, append it with `A: (awaiting answer)`.

```python
def _format_human_exchanges(exchanges: list[HumanExchange]) -> str:
    if not exchanges:
        return "None."
    parts = []
    for e in exchanges:
        answer_str = e.answer if e.answer is not None else "(awaiting answer)"
        parts.append(f"Q: {e.question}\nContext: {e.context}\nA: {answer_str}")
    return "\n\n".join(parts)
```

### `redirect_instructions_block`

Only rendered when `state.redirect_instructions` is non-empty:

```
## Active redirect instructions (follow these above all else)
1. {first instruction}
2. {second instruction}
...
```

If the list is empty, the `## Redirect instructions` section header and block are both omitted
entirely from the rendered prompt (the template substitution produces an empty string for that
section).

```python
def _format_redirect_instructions(instructions: list[str]) -> str:
    if not instructions:
        return ""
    lines = ["## Active redirect instructions (follow these above all else)"]
    for i, instr in enumerate(instructions, 1):
        lines.append(f"{i}. {instr}")
    return "\n".join(lines)
```

### `questions_asked`

Count only completed exchanges (those with a non-None `answer`), not the current pending one:

```python
questions_asked = len([e for e in state.human_exchanges if e.answer is not None])
```

### Full `build_supervisor_context()` Function

```python
def build_supervisor_context(state: BugTriageState) -> str:
    redirect_block = _format_redirect_instructions(state.redirect_instructions)

    # Build the full prompt body; omit redirect section header if block is empty
    if redirect_block:
        redirect_section = f"## Redirect instructions\n{redirect_block}"
    else:
        redirect_section = ""

    questions_asked = len([e for e in state.human_exchanges if e.answer is not None])

    return (
        f"{redirect_section}\n\n"
        f"## Current state\n"
        f"Iteration: {state.iterations} / {state.max_iterations}\n"
        f"Questions asked so far: {questions_asked} / 2\n\n"
        f"## Findings so far\n"
        f"{_format_findings(state.findings)}\n\n"
        f"## Human exchanges so far\n"
        f"{_format_human_exchanges(state.human_exchanges)}\n\n"
        f"## Your task\n"
        "Decide the next step. Output JSON with these fields:\n"
        "- next_node: one of \"investigator\", \"codebase_search\", \"web_search\", "
        "\"critic\", \"human_input\", \"writer\", \"end\"\n"
        "- reasoning: your chain-of-thought for this decision (1-3 sentences)\n"
        "- question: the question to ask the user (only when next_node == \"human_input\", "
        "otherwise null)\n"
        "- question_context: additional context to show alongside the question (null otherwise)\n"
        "- confidence: your confidence in the current root cause hypothesis (0.0-1.0). "
        "Use 0.0 if no hypothesis yet."
    ).strip()
```

---

## 5. `SupervisorDecision` Validation & Error Recovery

### Schema

```python
from typing import Literal
from pydantic import BaseModel

class SupervisorDecision(BaseModel):
    next_node: Literal[
        "investigator", "codebase_search", "web_search",
        "critic", "human_input", "writer", "end"
    ]
    reasoning: str
    question: str | None          # only when next_node == "human_input"
    question_context: str | None  # only when next_node == "human_input"
    confidence: float             # 0.0–1.0
```

### Error Recovery Strategy

`llm.with_structured_output(SupervisorDecision)` handles JSON parsing and passes the result
through Pydantic. Validation errors are rare with this approach but can occur with model drift
or unusual inputs.

The full retry logic lives exclusively in `_invoke_supervisor()` (§2) — a single `try/except`
inside a two-iteration loop. `supervisor_node()` has no exception handling. This follows the
project rule against nested try-catches (PRD-007 §Architecture policy).

**Attempt 1 (initial):** Normal invocation. If a `ValidationError` or other exception is
raised, the loop appends a correction suffix to the messages and continues to attempt 2.

**Attempt 2 (correction):** Re-invoke with the original messages plus:

```
Your previous response was invalid. Error: {validation_error}
Please respond again with valid JSON matching the schema exactly.
The next_node field must be one of: investigator, codebase_search, web_search,
critic, human_input, writer, end.
```

**After second failure:** Log the error and return `_FORCED_FALLBACK` — a pre-constructed
`SupervisorDecision(next_node="writer", ...)` — without raising. The exception does not
propagate; the graph routes to writer and completes.

This matches the error table entry in PRD-003: *"Supervisor outputs invalid JSON → Pydantic
validation catches it; supervisor is re-invoked once with an error correction prompt."*

---

## 6. Routing Guards (Code Level)

Routing guards are applied in `route_from_supervisor()` **after** the supervisor LLM call,
overriding the LLM's decision when hard invariants would be violated. Guards fire regardless of
confidence or reasoning quality.

```python
def route_from_supervisor(state: BugTriageState) -> str:
    decision_node = state.get("next_node")

    # Guard 1: investigator-first invariant
    if state["iterations"] == 0 and decision_node != "investigator":
        return "investigator"

    # Guard 2: max human questions enforced in code, not just prompt
    if len(state["human_exchanges"]) >= 2 and decision_node == "human_input":
        return "codebase_search"

    # Guard 3: iteration limit
    if state["iterations"] >= state["max_iterations"]:
        return "writer"

    # Guard 4: supervisor must not end without a report
    if decision_node == "end" and state["report"] is None:
        return "writer"

    return decision_node
```

### Guard Reference Table

| Condition | Override | Rationale |
|---|---|---|
| `state.iterations == 0` and `decision.next_node != "investigator"` | Force `"investigator"` | LLM compliance not guaranteed; investigator-first is a hard invariant |
| `len(state.human_exchanges) >= 2` and `decision.next_node == "human_input"` | Force `"codebase_search"` | Max 2 questions enforced in code, not just prompt |
| `state.iterations >= state.max_iterations` | Force `"writer"` | Prevents infinite loops |
| `decision.next_node == "end"` and `state.report is None` | Force `"writer"` | Supervisor should not end without a report |

---

## 7. Confidence Thresholds

Thresholds are embedded in the system prompt (§3) and enforced via the prompt. The routing
guard does not check confidence directly — the LLM is trusted to follow the threshold
instructions once given them explicitly. The `max_iterations` guard (§6, Guard 3) is the
code-level backstop if the LLM misapplies a threshold.

| Threshold | Condition | Action |
|---|---|---|
| 0.85 | Single high-quality finding | LLM may proceed to writer |
| 0.70 | Two or more corroborating findings | LLM may proceed to writer |
| < 0.70 | After investigator only | Must call at least one more agent |
| any | `max_iterations` reached | Forced to writer by routing guard regardless of confidence |

The `confidence` field in `SupervisorDecision` is stored in `supervisor_reasoning` context and
surfaced in LangSmith traces. It is not currently stored separately in `BugTriageState` but may
be added as an additive field in a future schema version.

---

## 8. Prompt Versioning

In-flight jobs are safe across prompt updates. LangGraph checkpoints store `BugTriageState`
(data), not the prompt string. A prompt change takes effect on the next supervisor invocation
regardless of whether the job was started before or after the change — the new prompt is
assembled from the current state data at invocation time.

**No migration is needed** for prompt-only changes. The only risk: if a prompt change alters
the *meaning* of a state field that is already partially populated (e.g. renaming a node that
appears in `supervisor_reasoning` or `redirect_instructions`), use the schema versioning
mechanism in PRD-003 §Schema Versioning to add a migration branch and bump
`_CURRENT_SCHEMA_VERSION`.

**Prompt storage:** The system prompt string lives in `nodes/prompts.py`
(`build_supervisor_system_prompt()`). It is a plain function, not loaded from a database or
external store. To update the prompt, edit the source file and redeploy. In-flight jobs pick up
the change at their next supervisor node execution.
