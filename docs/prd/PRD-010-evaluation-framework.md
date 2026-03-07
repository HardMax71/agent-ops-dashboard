---
id: PRD-010
title: Evaluation Framework
status: DRAFT
domain: evaluation
depends_on: [PRD-001, PRD-004, PRD-005]
key_decisions: [llm-as-judge-cross-family, golden-dataset-structure, ci-eval-gate, eval-staging-isolation]
---

# PRD-010 — Evaluation Framework

| Field        | Value                                          |
|--------------|------------------------------------------------|
| Document ID  | PRD-010                                        |
| Version      | 1.0                                            |
| Status       | DRAFT                                          |
| Date         | March 2026                                     |
| Parent Doc   | [PRD-001](PRD-001-master-overview.md)          |
| Related Docs | [PRD-004](PRD-004-agent-layer.md) (Agent Layer), [PRD-005](PRD-005-langsmith-observability.md) (LangSmith Observability) |

---

## Overview

This document specifies the evaluation framework for AgentOps Dashboard: how agent output quality is
measured, what data is used as ground truth, how scores are computed, and how evaluations are gated
in CI.

The framework is built on LangSmith's evaluation primitives (datasets, evaluators, experiments) and
runs automatically on every prompt change and deployment.

---

## Evaluation Dimensions

### What Gets Evaluated

The eval framework measures three things:

| Dimension             | Question                                                             | Evaluator Type                                    |
|-----------------------|----------------------------------------------------------------------|---------------------------------------------------|
| **Triage Accuracy**   | Does the root cause match what a human engineer would identify?      | LLM-as-judge + human comparison                   |
| **Report Usefulness** | Is the final report helpful and actionable?                          | LLM-as-judge (rubric)                             |
| **Question Quality**  | When the supervisor asks the user a question, is it a good question? | Human feedback (thumbs up/down in UI)             |
| **Agent Efficiency**  | Did the supervisor route optimally (no redundant agent calls)?       | Automated: count supervisor hops vs. minimum path |

---

## LLM-as-Judge Setup

```python
from typing import Literal
from pydantic_settings import BaseSettings
from langchain_anthropic import ChatAnthropic
from langsmith.evaluation import evaluate, LangChainStringEvaluator


class EvalSettings(BaseSettings):
    langchain_project: Literal["agentops-staging"]  # fails fast if pointed at production
    langsmith_api_key: str                           # required to submit eval results to LangSmith
    langserve_base_url: str                          # must be a staging deployment URL
    openai_api_key: str                              # separate eval project key for billing isolation

settings = EvalSettings()  # raises ValidationError if env vars are missing or wrong

helpfulness_evaluator = LangChainStringEvaluator(
    "criteria",
    config={
        "criteria": {
            "helpfulness": "Is this triage report specific, actionable, and correct?",
            "completeness": "Does the report cover severity, root cause, relevant files, and a fix suggestion?",
            "accuracy": "Does the root cause match the reference answer?"
        },
        "llm": ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    }
)

results = evaluate(
    lambda inputs: run_triage_job(inputs["issue_url"]),
    data="agentops-golden-dataset-v1",
    evaluators=[helpfulness_evaluator],
    experiment_prefix="prompt-change-2026-03",
)
```

The judge uses a different model family (Anthropic) than the production agents (OpenAI GPT-4o) to
avoid self-preference bias, which research shows inflates scores by 10–25% when a model evaluates
its own outputs.

---

## Scoring Rubric

| Score | Meaning                                                                             |
|-------|-------------------------------------------------------------------------------------|
| 5     | Perfect: root cause is correct, files are exact, report is clear and actionable     |
| 4     | Good: root cause is correct, minor gaps in files or report formatting               |
| 3     | Partial: hypothesis is on the right track but root cause is incomplete or imprecise |
| 2     | Poor: wrong code area identified, or report is too vague to be actionable           |
| 1     | Fail: completely wrong diagnosis or empty output                                    |

**Target:** Average score ≥ 4.0 / 5.0 on the golden dataset before any prompt change is deployed to production.

---

## Golden Dataset

### Structure

The golden dataset is a collection of real GitHub issues with human-authored reference answers:

```python
{
    "issue_url": "https://github.com/org/repo/issues/1042",
    "issue_title": "Auth token expiry causes 500 on /api/me",
    "issue_body": "...",
    "reference": {
        "severity": "HIGH",
        "root_cause": "JWT expiry check in auth/middleware.py:L142 uses local time instead of UTC",
        "relevant_files": ["auth/middleware.py", "tests/test_auth.py"],
        "expected_keywords": ["JWT", "UTC", "timezone", "token expiry"]
    }
}
```

### Dataset Growth Plan

| Phase       | Dataset Size | Source                                      |
|-------------|--------------|---------------------------------------------|
| v1.0 launch | 20 issues    | Manually authored from real repos           |
| v1.1        | 50 issues    | User feedback thumbs up/down on job outputs |
| v2.0        | 200+ issues  | Crowdsourced from community contributors    |

### Dataset Management

The golden dataset is managed in LangSmith's Datasets UI. New examples can be added directly from a LangSmith trace: if
a live production job produces a high-quality output, it can be added to the dataset in one click via LangSmith's "Add
to Dataset" feature.

---

## Automated Eval Pipeline

### When Evals Run

| Trigger                                         | Action                                                                          |
|-------------------------------------------------|---------------------------------------------------------------------------------|
| Any agent prompt change proposed in a PR to `main` | CI pipeline runs eval against golden dataset; fails PR if avg score drops > 0.3 |
| New LangServe agent version deployed to staging | Eval runs automatically; results posted to PR as a comment                      |
| Daily at 02:00 UTC                              | Production eval: random sample of 10 recent jobs scored and logged              |
| Manual trigger                                  | Developer can run evals on demand from LangSmith UI or CLI                      |

### CI Integration

```yaml
# .github/workflows/eval.yml
- name: Run LangSmith Evals
  run: |
    python scripts/run_evals.py \
      --dataset agentops-golden-dataset-v1 \
      --project agentops-staging \
      --min-score 4.0 \
      --fail-on-regression
```

### Eval Environment Requirements

CI-triggered evals (PR gate and staging-deploy trigger) call `run_triage_job` against the
golden dataset. They must run in a fully isolated environment:

| Resource          | Production value          | Eval (CI) value                        | Why                                                                |
|-------------------|---------------------------|----------------------------------------|--------------------------------------------------------------------|
| LangSmith project | `agentops-prod`           | `agentops-staging`                     | Prevent eval traces from polluting production dashboards           |
| LangServe URL     | `https://agents.prod/…`   | `https://agents.staging/…`             | Prevent eval traffic from consuming production rate-limit budget   |
| OpenAI API key    | Production org/project    | Separate org sub-account or project    | Billing isolation; eval cost tracked separately from user traffic  |

**Staging deployment requirement:** A dedicated staging deployment of all LangServe agents
(`investigator`, `codebase-search`, `web-search`, `critic`, `writer`) must be maintained and
kept in sync with `main`. CI evals fail if the staging deployment is unreachable.

**Daily production eval (02:00 UTC)** is exempt from the above: it scores completed job
outputs already stored in LangSmith and does not call `run_triage_job` on new inputs.
Production credentials are appropriate for that trigger.

**CI env vars (set in GitHub Actions secrets):**

{% raw %}
```yaml
LANGCHAIN_PROJECT: agentops-staging
LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_STAGING_KEY }}
LANGSERVE_BASE_URL: ${{ secrets.LANGSERVE_STAGING_URL }}
OPENAI_API_KEY: ${{ secrets.OPENAI_EVAL_KEY }}
```
{% endraw %}
