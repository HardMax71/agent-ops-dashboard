"""CLI entrypoint: export the Strawberry schema as SDL to schemas/schema.graphql."""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    # Provide dummy env vars so Settings() can instantiate during codegen
    os.environ.setdefault("JWT_SECRET", "export-dummy-secret-must-be-32-chars!")
    os.environ.setdefault("ENVIRONMENT", "development")

    from agentops.graphql.schema import schema

    project_root = Path(__file__).resolve().parent.parent.parent
    dest = project_root / "schemas" / "schema.graphql"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(schema.as_str())
    import sys

    sys.stdout.write(f"wrote {dest}\n")


if __name__ == "__main__":
    main()
