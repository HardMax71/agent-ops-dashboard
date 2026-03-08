#!/usr/bin/env python3
"""LangSmith evaluation runner for AgentOps Dashboard.

Usage:
    python scripts/run_evals.py --dataset agentops-golden-dataset-v1 --min-score 4.0
"""
from __future__ import annotations

import argparse
import os
import sys

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langsmith import Client
from langsmith.evaluation import evaluate
from pydantic import BaseModel, Field


class EvalScore(BaseModel):
    score: float = Field(ge=1.0, le=5.0)
    reasoning: str


_HELPFULNESS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are evaluating the quality of a bug triage report. Score from 1-5 where 5 is excellent."),
    ("human", "Issue: {question}\n\nTriage Report: {answer}\n\nScore the helpfulness of this report (1-5):"),
])

_judge_llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
_helpfulness_chain = _HELPFULNESS_PROMPT | _judge_llm.with_structured_output(EvalScore)


def helpfulness_evaluator(run, example) -> dict:  # noqa: ANN001
    """Evaluate helpfulness of triage report."""
    answer = str(run.outputs.get("report", "") if run.outputs else "")
    question = str(example.inputs.get("issue_body", "") if example.inputs else "")
    result = _helpfulness_chain.invoke({"question": question, "answer": answer})
    return {"key": "helpfulness", "score": result.score / 5.0}


def file_relevance_evaluator(run, example) -> dict:  # noqa: ANN001
    """Evaluate file relevance overlap."""
    predicted = set(run.outputs.get("relevant_files", []) if run.outputs else [])
    expected = set(example.outputs.get("relevant_files", []) if example.outputs else [])
    if not expected:
        return {"key": "file_relevance", "score": 1.0}
    overlap = len(predicted & expected) / len(expected)
    return {"key": "file_relevance", "score": overlap}


def severity_match_evaluator(run, example) -> dict:  # noqa: ANN001
    """Evaluate severity classification accuracy."""
    predicted = (run.outputs or {}).get("severity", "")
    expected = (example.outputs or {}).get("severity", "")
    return {"key": "severity_match", "score": 1.0 if predicted == expected else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LangSmith evaluations")
    parser.add_argument("--dataset", required=True, help="LangSmith dataset name")
    parser.add_argument("--min-score", type=float, default=4.0, help="Minimum average score to pass")
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
        lambda inputs: inputs,  # Placeholder — real evaluations use actual chain
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
