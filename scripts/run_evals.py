#!/usr/bin/env python3
"""LangSmith evaluation runner for AgentOps Dashboard.

Usage:
    python scripts/run_evals.py --dataset agentops-golden-dataset-v1 --min-score 0.8
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from langsmith import Client
from langsmith.evaluation import evaluate
from langsmith.schemas import Example, Run
from pydantic import BaseModel, Field

from agentops.graph.graph import build_graph
from agentops.graph.state import BugTriageState, TriageReport


class EvalScore(BaseModel):
    score: float = Field(ge=1.0, le=5.0)
    reasoning: str


_HELPFULNESS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are evaluating the quality of a bug triage report. "
            "Score from 1-5 where 5 is excellent.",
        ),
        (
            "human",
            "Issue: {question}\n\nTriage Report: {answer}\n\n"
            "Score the helpfulness of this report (1-5):",
        ),
    ]
)

_judge_llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
_helpfulness_chain = _HELPFULNESS_PROMPT | _judge_llm.with_structured_output(EvalScore)


def helpfulness_evaluator(run: Run, example: Example) -> dict[str, object]:
    """Evaluate helpfulness of triage report."""
    answer = str(run.outputs.get("report", "") if run.outputs else "")
    question = str(example.inputs.get("issue_body", "") if example.inputs else "")
    result = _helpfulness_chain.invoke({"question": question, "answer": answer})
    return {"key": "helpfulness", "score": result.score / 5.0}


def file_relevance_evaluator(run: Run, example: Example) -> dict[str, object]:
    """Evaluate file relevance overlap."""
    predicted = set(run.outputs.get("relevant_files", []) if run.outputs else [])
    expected = set(example.outputs.get("relevant_files", []) if example.outputs else [])
    if not expected:
        return {"key": "file_relevance", "score": 1.0}
    overlap = len(predicted & expected) / len(expected)
    return {"key": "file_relevance", "score": overlap}


def severity_match_evaluator(run: Run, example: Example) -> dict[str, object]:
    """Evaluate severity classification accuracy."""
    predicted = (run.outputs or {}).get("severity", "")
    expected = (example.outputs or {}).get("severity", "")
    return {"key": "severity_match", "score": 1.0 if predicted == expected else 0.0}


def _format_report_text(report: TriageReport) -> str:
    """Format a TriageReport as readable text for LLM-as-judge evaluation."""
    parts = [
        f"Severity: {report.severity}",
        f"Root Cause: {report.root_cause}",
        f"Recommended Fix: {report.recommended_fix}",
    ]
    if report.relevant_files:
        parts.append(f"Relevant Files: {', '.join(report.relevant_files)}")
    return "\n".join(parts)


async def _invoke_triage(inputs: dict[str, str]) -> dict[str, object]:
    """Invoke the full triage graph on a single eval example.

    Builds a fresh graph with an in-memory checkpointer per example so
    each evaluation run is fully isolated.  The returned dict matches the
    keys expected by the three evaluators (report, relevant_files,
    severity).
    """
    job_id = f"eval-{uuid.uuid4()}"
    graph = build_graph(checkpointer=MemorySaver())

    initial_state = BugTriageState(
        job_id=job_id,
        issue_url=inputs.get("issue_url", ""),
        issue_title=inputs.get("issue_title", ""),
        issue_body=inputs.get("issue_body", ""),
        repository=inputs.get("repository", ""),
    )

    result = await graph.ainvoke(
        initial_state.model_dump(),
        config={"configurable": {"thread_id": job_id}},
    )

    final_state = BugTriageState.model_validate(result)

    if final_state.report is not None:
        report = final_state.report
        report_text = report.github_comment or _format_report_text(report)
        return {
            "report": report_text,
            "relevant_files": report.relevant_files,
            "severity": report.severity,
        }
    return {"report": "", "relevant_files": [], "severity": "medium"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LangSmith evaluations")
    parser.add_argument("--dataset", required=True, help="LangSmith dataset name")
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.8,
        help="Minimum average score",
    )
    args = parser.parse_args()

    if not os.environ.get("LANGSMITH_API_KEY"):
        print("WARNING: LANGSMITH_API_KEY not set — skipping evaluations")
        sys.exit(0)

    client = Client()

    # Check dataset exists
    datasets = list(client.list_datasets(dataset_name=args.dataset))
    if not datasets:
        print(f"WARNING: Dataset '{args.dataset}' not found in LangSmith — skipping evaluations")
        sys.exit(0)

    results = evaluate(
        _invoke_triage,
        data=args.dataset,
        evaluators=[helpfulness_evaluator, file_relevance_evaluator, severity_match_evaluator],
        experiment_prefix="agentops-eval",
        client=client,
    )

    scores: list[float] = []
    for r in results:
        score = r.get("score")
        if score is not None:
            scores.append(float(score))

    avg_score = sum(scores) / len(scores) if scores else 0.0
    print(f"Average score: {avg_score:.2f} (min: {args.min_score})")

    if avg_score < args.min_score:
        print(f"FAILED: score {avg_score:.2f} < minimum {args.min_score}")
        sys.exit(1)
    print("PASSED")


if __name__ == "__main__":
    main()
