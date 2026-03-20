import subprocess
import tempfile
from pathlib import Path

import redis.asyncio as aioredis
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from agentops.config import get_settings
from agentops.index.builder import _chunk_repository
from agentops.index.collection import collection_name
from agentops.models.worker_ctx import WorkerContext


async def build_codebase_index(
    ctx: WorkerContext,
    repository: str,
) -> None:
    """Build vector index for a repository."""
    redis: aioredis.Redis = ctx["redis"]
    settings = get_settings()
    col_name = collection_name(repository)
    lock_key = f"index_lock:{col_name}"

    # Per-repo Redis lock
    lock = redis.lock(lock_key, timeout=3600)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        return  # Already building

    try:
        repo_url = f"https://github.com/{repository}.git"
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(  # noqa: S603
                ["git", "clone", "--depth=1", repo_url, tmpdir],  # noqa: S607
                check=True,
                capture_output=True,
            )
            documents_raw = _chunk_repository(Path(tmpdir))

        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        docs = [
            Document(page_content=str(d["content"]), metadata=d["metadata"]) for d in documents_raw
        ]
        Chroma.from_documents(
            docs,
            embeddings,
            collection_name=col_name,
            persist_directory=settings.chroma_persist_dir,
        )
    finally:
        await lock.release()


async def update_codebase_index(
    ctx: WorkerContext,
    repository: str,
    base_sha: str,
    head_sha: str,
) -> None:
    """Update vector index for changed files (incremental on push webhook)."""
    repo_url = f"https://github.com/{repository}.git"
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(  # noqa: S603
            ["git", "clone", "--depth=50", repo_url, tmpdir],  # noqa: S607
            check=True,
            capture_output=True,
        )
        result = subprocess.run(  # noqa: S603
            ["git", "diff", "--name-only", f"{base_sha}..{head_sha}"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]

    if not changed_files:
        return

    # Re-index all changed files — simplified approach
    await build_codebase_index(ctx, repository)
