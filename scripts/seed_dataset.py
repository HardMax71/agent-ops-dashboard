"""Seed LangSmith golden dataset from fixture files.

Usage:
    python scripts/seed_dataset.py [--dataset agentops-golden-dataset-v1]
"""

import argparse
import json
from pathlib import Path

from langsmith import Client

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "issues"
DEFAULT_DATASET = "agentops-golden-dataset-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed LangSmith golden dataset")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Dataset name in LangSmith")
    args = parser.parse_args()

    client = Client()

    # Create or fetch existing dataset
    datasets = list(client.list_datasets(dataset_name=args.dataset))
    if datasets:
        dataset = datasets[0]
        print(f"Using existing dataset: {dataset.name} (id={dataset.id})")
    else:
        dataset = client.create_dataset(
            dataset_name=args.dataset,
            description="Golden evaluation dataset for AgentOps triage pipeline",
        )
        print(f"Created dataset: {dataset.name} (id={dataset.id})")

    # Load and push all fixture files
    fixture_files = sorted(FIXTURES_DIR.glob("issue_*.json"))
    print(f"Found {len(fixture_files)} fixture files")

    for fixture_path in fixture_files:
        with open(fixture_path) as f:
            fixture = json.load(f)

        inputs = {
            "issue_url": fixture["issue_url"],
            "issue_title": fixture["issue_title"],
            "issue_body": fixture["issue_body"],
            "repository": fixture["repository"],
        }
        outputs = fixture.get("outputs", {})

        client.create_example(
            inputs=inputs,
            outputs=outputs,
            dataset_id=dataset.id,
        )
        print(f"  Added: {fixture_path.name} — {fixture['issue_title'][:60]}")

    print(f"\nDone. {len(fixture_files)} examples pushed to '{args.dataset}'.")


if __name__ == "__main__":
    main()
