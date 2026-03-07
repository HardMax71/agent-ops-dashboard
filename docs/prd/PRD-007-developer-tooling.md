# PRD-007 — Python Developer Tooling & Code Quality Standards

## Metadata

| Field        | Value                                                                                                                                                                                              |
|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Document ID  | PRD-007                                                                                                                                                                                            |
| Version      | 1.0                                                                                                                                                                                                |
| Status       | DRAFT                                                                                                                                                                                              |
| Date         | March 2026                                                                                                                                                                                         |
| Author       | Engineering Team                                                                                                                                                                                   |
| Parent       | [PRD-001](PRD-001-master-overview.md)                                                                                                                                                              |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md) (BugTriageState TypedDict question), [PRD-006](PRD-006-data-validation.md) (Pydantic validation patterns) |

---

## Table of Contents

1. [Philosophy](#1-philosophy)
2. [Python Version](#2-python-version)
3. [Package & Environment Management: uv](#3-package--environment-management-uv)
4. [Dependency Groups (PEP 735)](#4-dependency-groups-pep-735)
5. [Linting & Formatting: ruff](#5-linting--formatting-ruff)
6. [Type Checking: ty](#6-type-checking-ty)
7. [Python 3.12+ Type System Standards](#7-python-312-type-system-standards)
8. [Docstring Standards](#8-docstring-standards)
9. [TypedDict vs Pydantic BaseModel: Decision Guide](#9-typeddict-vs-pydantic-basemodel-decision-guide)
10. [Pre-commit & CI](#10-pre-commit--ci)
11. [pytest Configuration](#11-pytest-configuration)

---

## 1. Philosophy

One tool per concern, all from the **Astral stack** (`uv` + `ruff` + `ty`) — consistent, fast, Rust-based, zero config
drift. Standards are enforced by tooling, not code review. If `ruff` passes and `ty` passes, the code is correct by
definition of the project's quality bar.

The `pyproject.toml` is the single source of truth for packaging, tool config, and dependency declarations. No
`setup.py`, no `requirements.txt`, no `.flake8`, no `mypy.ini`.

---

## 2. Python Version

- **Minimum: Python 3.12** (managed by `uv`)
- `.python-version` file pins the exact version: `3.12`
- `requires-python = ">=3.12"` declared in `pyproject.toml`

Python 3.12 enables:
- `type X = ...` type alias syntax (PEP 695)
- Full PEP 695 generic syntax (`class Foo[T]: ...`)
- `ExceptionGroup` for structured exception handling
- `tomllib` in stdlib (no external dep for TOML parsing)

---

## 3. Package & Environment Management: `uv`

`uv` replaces `pip`, `venv`, `pip-tools`, and `pipx` in a single binary. It is the only tool used to manage
Python environments and dependencies on this project.

### Key Commands

```bash
uv sync                          # install project + dev dependencies (dev group is default)
uv sync --all-groups             # install project + all dependency groups (dev + test)
uv sync --only-dev               # install dev tooling only — no project or runtime deps (CI linting)
uv add fastapi                   # add a runtime dependency to [project].dependencies
uv add --group dev ruff          # add a dev dependency to [dependency-groups].dev
uv run pytest                    # run pytest in the managed venv
uv run ruff check .              # run ruff in the managed venv
uv run ty check src/             # run ty in the managed venv
```

### pyproject.toml — uv-owned sections

```toml
[project]
name = "agent-ops-dashboard"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv]
# uv-specific settings (index configuration, etc.)
```

---

## 4. Dependency Groups (PEP 735)

Groups are declared in `[dependency-groups]` (PEP 735), **not** `[project.optional-dependencies]`. This is the
`uv`-preferred approach and avoids the semantic misuse of optional deps for developer tooling.

```toml
[project]
dependencies = [
    # Runtime — always installed in production
    "fastapi>=0.115",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "langgraph>=0.2",
    "langchain>=0.3",
    "langchain-openai>=0.2",
    "langserve>=0.3",
    "arq>=0.26",
    "redis>=5.0",
    "httpx>=0.27",
    "uvicorn[standard]>=0.30",
    "langsmith>=0.1",
]

[dependency-groups]
dev = [
    "ruff>=0.6",
    "ty>=0.0.1a1",      # Astral type checker — pinned to alpha while stabilising
    "pre-commit>=3.8",
]
test = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",      # AsyncClient for FastAPI test client
    "pytest-cov>=5.0",
]
```

### Why three groups

| Group          | Purpose                                               | Installed in      |
|----------------|-------------------------------------------------------|-------------------|
| `dependencies` | Ships in production — the running application         | prod + CI + dev   |
| `dev`          | Linters, type checker, pre-commit — developer tooling | dev VMs only      |
| `test`         | Test runtime — pytest, coverage                       | CI test runners + dev |

---

## 5. Linting & Formatting: `ruff`

`ruff` replaces: `black`, `isort`, `flake8`, `pyupgrade`, `pydocstyle`, `flake8-annotations`. One binary, one
config block in `pyproject.toml`, sub-millisecond on incremental runs.

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "UP",   # pyupgrade — enforces Python 3.12+ syntax
    "D",    # pydocstyle — 100% docstring coverage on public API
    "ANN",  # flake8-annotations — all functions must be typed
    "RUF",  # ruff-specific rules
    "S",    # flake8-bandit security lint (subset)
]
ignore = [
    "D100",   # missing module docstring — optional at module level
    "D104",   # missing package docstring
    "ANN101", # self annotation — never required
    "ANN102", # cls annotation — never required
]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.isort]
known-first-party = ["agent_ops_dashboard"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### Docstring coverage via `D` rules

All public classes, methods, and functions must have a Google-style docstring. Private (`_prefixed`) items are
exempt. This gives 100% coverage on the public API surface without noise on internals.

---

## 6. Type Checking: `ty`

`ty` is Astral's Rust-based type checker — same team as `ruff`/`uv`. As of 2025 it is in active alpha; the
project pins it with `>=0.0.1a1` and accepts minor churn during stabilisation.

```toml
[tool.ty]
python-version = "3.12"

[tool.ty.rules]
# All rules on by default in strict mode
```

Run: `uv run ty check src/`

### Why `ty` over `mypy`/`pyright`

| Criterion            | ty                                      | mypy / pyright                         |
|----------------------|-----------------------------------------|----------------------------------------|
| Toolchain alignment  | Same Astral ecosystem as ruff/uv        | Separate teams and config surfaces     |
| Performance          | Rust core — significantly faster        | Python (mypy) / Node (pyright)         |
| uv integration       | Native                                  | External install required              |
| Maturity             | Alpha — may hit edge-case gaps          | Mature, broad plugin ecosystem         |

**Trade-off:** `ty` is alpha. If a blocking issue is encountered, fall back to `pyright` (already in the Astral
orbit via Pylance). Document the blocker in this PRD when that decision is made.

---

## 7. Python 3.12+ Type System Standards

### 7.1 Forbidden Patterns (enforced by `ruff UP` + `ANN`)

| Forbidden | Replacement | Rule |
|-----------|-------------|------|
| `from typing import List, Dict, Tuple, Set` | `list`, `dict`, `tuple`, `set` (builtins) | UP035 |
| `Optional[X]` | `X \| None` | UP007 |
| `Union[X, Y]` | `X \| Y` | UP007 |
| `from typing import TypeAlias` + `X: TypeAlias = ...` | `type X = ...` (PEP 695) | UP040 |
| `Any` | Specific type, `TypeVar`, or `Protocol` | ANN401 |
| Untyped function parameter | Full annotation required | ANN001 |
| Untyped function return | Full annotation required | ANN201 |
| Local import (inside a function or method body) | Move to module-level | E402 |
| `if TYPE_CHECKING:` / `TYPE_CHECKING` (any use) | Fix the underlying issue: extract shared types into a dedicated `models.py` or `types.py`; no import guard patterns | arch |

### 7.2 Still-valid `typing` imports (not deprecated)

These have no builtin replacements and remain correct to import from `typing`:

`Annotated`, `TypeVar`, `ParamSpec`, `TypeVarTuple`, `Protocol`, `overload`, `ClassVar`, `Final`, `Literal`,
`TypeGuard`, `Never`, `Self`, `Unpack`

`TYPE_CHECKING` is explicitly forbidden. It is a symptom of import cycles or over-eager imports —
both of which are architecture problems. Circular imports must be resolved by restructuring (extract
shared types to a dedicated module). Annotation-only imports must be moved to module level; `from __future__ import annotations`
makes all annotations lazy at zero cost, eliminating any runtime import overhead. Disable the `TCH` ruff ruleset
accordingly.

### 7.3 No `Any`

`ANN401` is enabled. The only valid escape hatch is `object` (the true top type) when a genuine heterogeneous
container is needed. Annotate with a comment explaining why `Any` cannot be avoided if the linter is suppressed
via `# noqa: ANN401`.

### 7.4 Comment Policy

Inline comments inside function bodies are forbidden except for one purpose: explaining **how** a
non-obvious implementation works — a quirk, a subtle invariant, or a non-obvious contract that the code
alone cannot convey.

Narrating what the code does is never allowed. If a line needs a comment to explain what it does, rewrite
the line so it is self-explanatory (better name, extracted function, etc.).

| Allowed | Forbidden |
|---------|-----------|
| Docstrings at the top of a class or function | `# Validate state` before a validation call |
| `# getdel: atomic fetch-and-delete guarantees single-use` | `# Issue access token` before `jwt.encode(...)` |
| `# noqa: ANN401 — heterogeneous mapping, no bound type` | `# Step 1: fetch user` / `# Step 2: store token` |
| `7 * 24 * 3600,  # 7-day TTL — matches refresh token lifetime` | `# Call the GitHub API` |

This applies equally to TypeScript/JavaScript in the frontend: same rule, same exceptions.

---

## 8. Docstring Standards

Convention: **Google style** (enforced by `ruff D` + `convention = "google"`).

### Required on

- All public classes (`D101`)
- All public methods (`D102`)
- All public functions (`D103`)
- `__init__` methods when the class docstring does not describe args (`D107`)

### Template

```python
def fetch_issue(url: GitHubIssueUrl, token: str) -> GitHubIssue:
    """Fetch a GitHub issue via the REST API.

    Args:
        url: Validated GitHub issue URL.
        token: Personal access token with `repo` scope.

    Returns:
        Parsed issue data.

    Raises:
        GitHubAPIError: If the API returns a non-2xx response.
    """
```

---

## 9. TypedDict vs Pydantic BaseModel: Decision Guide

### The problem with TypedDict

`TypedDict` provides only static type hints — no runtime validation, no serialization helpers, no default values
without `NotRequired` boilerplate, no computed fields, no `frozen` immutability, and dict-access syntax
(`state["field"]`) instead of attribute access (`state.field`).

### Rule: use the right tool for the layer

| Use case | Type to use | Reason |
|----------|-------------|--------|
| LangGraph state (`BugTriageState`) | `TypedDict` | **Recommended** — `StateGraph` also accepts `BaseModel`/dataclass, but `TypedDict` is the idiomatic choice: nodes return partial dicts (only changed keys), LangGraph merges them cleanly; `BaseModel` state requires full model reconstruction per node update |
| API request / response bodies | Pydantic `BaseModel` | Runtime validation, automatic 422 response, `.model_dump()` |
| Internal structured data (`AgentFinding`, `HumanExchange`, `TriageReport`) | Pydantic `BaseModel` | Serialization to/from Redis, validation, attribute access |
| Supervisor LLM output (`SupervisorDecision`) | Pydantic `BaseModel` | `.with_structured_output()` accepts `TypedDict` / JSON schema too, but `BaseModel` is preferred: returns a validated object (not a raw dict), attribute access, validation errors surface cleanly (PRD-003 §5.2) |
| Simple config / constants | `dataclass(frozen=True)` | No runtime dep, immutable, attribute access |

### Implication for PRD-003

`AgentFinding`, `HumanExchange`, and `TriageReport` should be refactored from `TypedDict` to Pydantic `BaseModel`.
`BugTriageState` stays `TypedDict` — LangGraph supports `BaseModel` state too, but `TypedDict` is the
idiomatic choice: nodes return partial dicts with only the keys they update, which LangGraph merges
cleanly without requiring full model reconstruction. PRD-003 references this section for rationale.

### Example: correct boundary

```python
from __future__ import annotations

from typing import TypedDict
from pydantic import BaseModel


class BugTriageState(TypedDict):
    issue_url: str
    findings: list[AgentFinding]
    report: TriageReport | None


class AgentFinding(BaseModel):
    agent_name: str
    summary: str
    relevant_files: list[str]
    confidence: float


class TriageJobResponse(BaseModel):
    job_id: str
    status: str
    report: TriageReport | None = None
```

---

## 10. Pre-commit & CI

### Pre-commit (fast, local)

`ruff` runs on every commit via pre-commit hooks. `ty` is excluded from pre-commit — type checking is too slow
for a blocking commit hook on large diffs.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff          # lint + autofix
        args: [--fix]
      - id: ruff-format   # format
```

### CI pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml (relevant steps)
- name: Install dependencies
  run: uv sync --group dev --group test

- name: Lint
  run: uv run ruff check .

- name: Format check
  run: uv run ruff format --check .

- name: Type check
  run: uv run ty check src/

- name: Test
  run: uv run pytest --cov=src tests/
```

All four checks must pass for a PR to merge. There is no manual override — fix the code.

---

## 11. pytest Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"         # pytest-asyncio: no @pytest.mark.asyncio needed
testpaths = ["tests"]
addopts = "--strict-markers"

[tool.coverage.run]
source = ["src"]
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 80
```

### asyncio_mode = "auto"

All `async def test_*` functions are automatically treated as async tests. No per-test decorator required.
Consistent with the project's async-first architecture (FastAPI, ARQ, LangGraph async).

### Coverage threshold

80% line coverage is the minimum for CI to pass. New features must include tests that keep coverage above this
floor. Coverage reports are generated per-run; `fail_under = 80` is a hard gate, not a suggestion.
