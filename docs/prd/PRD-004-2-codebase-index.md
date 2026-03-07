---
id: PRD-004-2
title: Codebase Vector Index — Full Implementation Spec
status: DRAFT
domain: backend/agents
depends_on: [PRD-004]
key_decisions: [chroma-collection-naming, incremental-reindex, arq-indexer-job]
---

# PRD-004-2 — Codebase Vector Index: Full Implementation Spec

| Field        | Value                                                                 |
|--------------|-----------------------------------------------------------------------|
| Document ID  | PRD-004-2                                                             |
| Version      | 1.0                                                                   |
| Status       | DRAFT                                                                 |
| Date         | March 2026                                                            |
| Parent Doc   | [PRD-004](PRD-004-agent-layer.md)                                     |
| Related Docs | [PRD-004-1](PRD-004-1-agent-chains.md) (Chain specs, retriever usage) |

---

## 1. Purpose & Scope

This document provides the full implementation spec for the codebase vector index used by the
Codebase Search Agent. PRD-004 §Codebase Vector Index leaves four gaps that make it impossible to
implement:

1. `codebase_retriever` — package, collection naming, persist directory, and how to select the
   correct collection per repository are all unspecified.
2. Index build process — the ARQ job, clone mechanism, chunking API, and file filter are not shown.
3. Incremental re-index — "webhook or manual trigger" is hand-waved; the GitHub push event, git-diff
   mechanism, and partial Chroma update are completely unspecified.
4. Correct `from_language()` API — PRD-004 mentions language-aware splitting in prose but never uses
   the actual API.

**Boundary with PRD-004:** PRD-004 covers the strategic decision to use Chroma, the retriever
parameters (`k=8`, `score_threshold=0.3`), and the index lifecycle table. This document covers
*only* the concrete implementation details. Do not duplicate the overview here.

**Boundary with PRD-004-1:** PRD-004-1 imports `get_codebase_retriever` from this module and uses
it inside the Codebase Search Agent chain. The retriever interface is specified here; its usage in
the chain is specified there.

---

## 2. Package & Import

The correct package is `langchain-chroma` (a standalone package, not `langchain-community`):

```python
# Package: langchain-chroma  (pip install langchain-chroma)
from langchain_chroma import Chroma

# Text splitting with language-aware boundaries
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language

# Embeddings
from langchain_openai import OpenAIEmbeddings

# Retriever type hint
from langchain_core.vectorstores import VectorStoreRetriever
```

**Do not use** `langchain_community.vectorstores.Chroma` — that import path is deprecated and will
be removed in a future LangChain release.

---

## 3. Collection Naming Convention

One Chroma collection is created per repository. The collection name must be:

- Deterministic (same repo URL always maps to the same name)
- URL-safe (no slashes, colons, or special characters)
- Collision-resistant (two repos with similar names must not collide)

**Convention:** `repo_{sha256(repo_url)[:16]}`

```python
import hashlib


def collection_name(repo_url: str) -> str:
    """
    Return a deterministic, URL-safe Chroma collection name for a repository.

    Normalises the URL before hashing: strips trailing slashes and the .git
    suffix so that https://github.com/owner/repo, .../repo/, and .../repo.git
    all resolve to the same collection.

    Examples:
        "https://github.com/owner/repo"      → "repo_4a2f1b9c8d3e7f02"
        "https://github.com/owner/repo/"     → "repo_4a2f1b9c8d3e7f02"
        "https://github.com/owner/repo.git"  → "repo_4a2f1b9c8d3e7f02"
        "https://github.com/owner/other-repo" → "repo_9c1d3e5f7a2b4c8d"
    """
    normalised = repo_url.rstrip("/")
    if normalised.endswith(".git"):
        normalised = normalised[:-4]
    digest = hashlib.sha256(normalised.encode()).hexdigest()
    return f"repo_{digest[:16]}"
```

**Note:** `collection_name` normalises the URL before hashing — trailing slashes and `.git`
suffixes are stripped — so `https://github.com/owner/repo`, `.../repo/`, and `.../repo.git`
all map to the same collection. Callers must not pre-normalise; pass the raw URL.

---

## 4. Persist Directory & Docker Volume

**Persist directory inside the container:** `/data/chroma`

**Docker volume:** `chroma_data` mounted at `/data/chroma`. The volume persists across container
restarts and image upgrades.

All collections share one directory. Chroma manages internal subdirectories per collection — no
manual directory partitioning is needed.

### docker-compose Declaration

```yaml
services:
  agentops-codebase-search:
    image: agentops-codebase-search:latest
    volumes:
      - chroma_data:/data/chroma
    environment:
      - CHROMA_PERSIST_DIR=/data/chroma
      - OPENAI_API_KEY=${OPENAI_API_KEY}

  agentops-arq-worker:
    image: agentops-arq-worker:latest
    volumes:
      - chroma_data:/data/chroma   # worker writes; search service reads
    environment:
      - CHROMA_PERSIST_DIR=/data/chroma
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}

volumes:
  chroma_data:
```

**Important:** Both the `agentops-codebase-search` service and the `agentops-arq-worker` service
mount the same `chroma_data` volume. The search service only reads; the ARQ worker only writes
(protected by a per-repo Redis lock — see Section 8).

---

## 5. `codebase_retriever` Instantiation

### Function Signature

```python
import chromadb

def get_codebase_retriever(repository: str) -> VectorStoreRetriever:
    """
    Return a LangChain VectorStoreRetriever for the Chroma collection
    associated with the given repository URL.

    Args:
        repository: The repository URL as stored in BugTriageState.repository.
            e.g. "https://github.com/owner/repo"

    Returns:
        A VectorStoreRetriever configured with similarity search,
        k=8 results, and a minimum score threshold of 0.3.

    Raises:
        chromadb.errors.InvalidCollectionException: If the collection does not exist
            (repository has not been indexed yet). Propagates to the worker error handler.
    """
    coll_name = collection_name(repository.rstrip("/"))

    # Chroma(persist_directory=...) silently creates missing collections, so we
    # must validate existence via the raw client first. get_collection() raises
    # InvalidCollectionException if the name is not found — let it propagate.
    chromadb.PersistentClient(path="/data/chroma").get_collection(coll_name)

    vectorstore = Chroma(
        collection_name=coll_name,
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
        persist_directory="/data/chroma",
    )
    return vectorstore.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 8, "score_threshold": 0.3},
    )
```

### Call Site

`get_codebase_retriever` is called inside `codebase_search_node` (in the LangGraph orchestration
layer) before building the chain, using `state["repository"]`:

```python
async def codebase_search_node(state: BugTriageState) -> dict:
    retriever = get_codebase_retriever(state["repository"])
    chain = build_codebase_chain(retriever)  # see PRD-004-1 §6
    # ... invoke chain and translate finding
```

---

## 6. Index Build Process

### Trigger

The full index build is performed by an ARQ background job: `build_codebase_index(repo_url, force=False)`.

**Enqueue conditions** (checked by `POST /jobs` endpoint when a new job is submitted):

1. The repository has never been indexed (`repo_index_metadata` row does not exist).
2. The existing index is older than 24 hours (`indexed_at < now() - interval '24 hours'`).
3. `force=True` is passed explicitly (manual rebuild via admin API).

If a `build_codebase_index` job for the same repository is already queued or running, the enqueue
is skipped (ARQ deduplication via job ID = `build:{collection_name}`).

### Database Table

```sql
CREATE TABLE repo_index_metadata (
    repo_url     TEXT PRIMARY KEY,
    indexed_at   TIMESTAMPTZ NOT NULL,
    head_sha     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'  -- pending | building | ready | failed
);
```

### ARQ Job Implementation

```python
import os
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path

import chardet
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java"}
EXTENSION_TO_LANGUAGE = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".ts": Language.TS,
    ".go": Language.GO,
    ".java": Language.JAVA,
}
EXCLUDE_DIRS = {"node_modules", "dist", "__pycache__", ".git"}
EXCLUDE_FILENAME_PATTERNS = {"*.min.js", "*.min.css"}
MAX_REPO_SIZE_MB = 500


async def build_codebase_index(ctx, repo_url: str, force: bool = False):
    """
    ARQ job: clone repo, chunk source files, embed, store in Chroma.
    """
    col_name = collection_name(repo_url.rstrip("/"))
    redis = ctx["redis"]

    # Per-repo lock to prevent concurrent index builds
    lock_key = f"index_lock:{col_name}"
    async with redis.lock(lock_key, timeout=3600):
        await _do_build(repo_url, col_name)


async def _do_build(repo_url: str, col_name: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Size check before clone
        _check_repo_size(repo_url)

        # 2. Clone (shallow)
        github_token = os.environ["GITHUB_TOKEN"]
        auth_url = repo_url.replace("https://", f"https://{github_token}@")
        subprocess.run(
            ["git", "clone", "--depth=1", auth_url, tmpdir],
            check=True, capture_output=True,
        )

        # 3. Get HEAD SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmpdir, check=True, capture_output=True, text=True,
        )
        head_sha = result.stdout.strip()

        # 4. Collect and chunk source files
        docs = _chunk_repository(Path(tmpdir))

        # 5. Embed and store
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            collection_name=col_name,
            persist_directory="/data/chroma",
        )

    # 6. Update metadata
    await _update_metadata(repo_url, head_sha, status="ready")
    logger.info("index built: repo=%s collection=%s docs=%d", repo_url, col_name, len(docs))
```

### File Filter

```python
def _should_index(path: Path) -> bool:
    """Return True if the file should be indexed."""
    import fnmatch

    # Exclude excluded directories and hidden directories/files
    for part in path.parts:
        if part in EXCLUDE_DIRS or part.startswith("."):
            return False

    # Exclude minified files and other glob-matched filename patterns
    if any(fnmatch.fnmatch(path.name, pat) for pat in EXCLUDE_FILENAME_PATTERNS):
        return False

    # Extension allowlist
    if path.suffix not in SUPPORTED_EXTENSIONS:
        return False

    # Skip binary files (heuristic: chardet confidence < 0.9 for text)
    try:
        raw = path.read_bytes()[:4096]
        result = chardet.detect(raw)
        if result["confidence"] < 0.9 or result["encoding"] is None:
            return False
    except OSError:
        return False

    return True
```

### Language-Aware Chunking

```python
def _chunk_repository(repo_root: Path) -> list:
    """Chunk all indexable source files in the repository."""
    from langchain_core.documents import Document

    docs = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or not _should_index(path):
            continue

        language = EXTENSION_TO_LANGUAGE[path.suffix]
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=language,      # splits on language-specific syntax boundaries
            chunk_size=1000,
            chunk_overlap=200,
        )

        content = path.read_text(encoding="utf-8", errors="ignore")
        rel_path = str(path.relative_to(repo_root))

        chunks = splitter.create_documents(
            texts=[content],
            metadatas=[{"source": rel_path}],
        )
        docs.extend(chunks)

    return docs
```

### Supported Languages

| Extension | `Language` enum value  | Notes                              |
|-----------|------------------------|------------------------------------|
| `.py`     | `Language.PYTHON`      | Splits on class/def boundaries     |
| `.js`     | `Language.JS`          | Splits on function/arrow functions |
| `.ts`     | `Language.TS`          | Same as JS + type annotations      |
| `.go`     | `Language.GO`          | Splits on func declarations        |
| `.java`   | `Language.JAVA`        | Splits on class/method boundaries  |

---

## 7. Incremental Re-index

### Trigger: GitHub Push Webhook

**Webhook endpoint:** `POST /webhooks/github` on the main API server.

**GitHub event type:** `push` (configured in the repository's GitHub webhook settings with
content type `application/json`). Only push events to the default branch trigger a re-index.

**Webhook secret:** The `X-Hub-Signature-256` header must be validated using
`GITHUB_WEBHOOK_SECRET` from the environment before processing any payload.

### Webhook Payload Fields Used

```json
{
  "ref": "refs/heads/main",
  "before": "abc123",        // base SHA (previous HEAD)
  "after": "def456",         // new HEAD SHA
  "repository": {
    "clone_url": "https://github.com/owner/repo.git",
    "default_branch": "main"
  }
}
```

**Default branch check:** Only process if `ref == f"refs/heads/{repository.default_branch}"`.
Push events to feature branches are ignored.

### Incremental Update Flow

```
GitHub push → POST /webhooks/github
    ↓
Validate X-Hub-Signature-256
    ↓
Check: ref == default branch?  No → ignore
    ↓  Yes
Enqueue ARQ job: update_codebase_index(repo_url, base_sha=before, head_sha=after)
    ↓
ARQ worker acquires per-repo Redis lock
    ↓
git diff --name-only {base_sha}..{head_sha}  → list of changed file paths
    ↓
For each changed file path:
    Delete Chroma documents where metadata["source"] == changed_file_path
    Re-chunk and re-embed the changed file
    Add new documents to Chroma collection
    ↓
Update repo_index_metadata: head_sha = after, indexed_at = now()
```

### ARQ Job Implementation

```python
async def update_codebase_index(ctx, repo_url: str, base_sha: str, head_sha: str):
    """
    ARQ job: incrementally re-index only the files changed between base_sha and head_sha.
    Falls back to full re-index if base_sha is not available in the shallow clone.
    """
    col_name = collection_name(repo_url.rstrip("/"))
    redis = ctx["redis"]

    async with redis.lock(f"index_lock:{col_name}", timeout=3600):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Clone the default branch (shallow)
            github_token = os.environ["GITHUB_TOKEN"]
            auth_url = repo_url.replace("https://", f"https://{github_token}@")
            subprocess.run(
                ["git", "clone", "--depth=50", auth_url, tmpdir],
                check=True, capture_output=True,
            )

            # Get changed files via git diff
            diff_result = subprocess.run(
                ["git", "diff", "--name-only", f"{base_sha}..{head_sha}"],
                cwd=tmpdir, capture_output=True, text=True,
            )

            if diff_result.returncode != 0:
                # base_sha not found (force push or too shallow) — fall back to full re-index
                logger.warning(
                    "base_sha %s not found for %s; falling back to full re-index",
                    base_sha, repo_url,
                )
                await _do_build(repo_url, col_name)
                return

            changed_files = [
                f for f in diff_result.stdout.strip().splitlines() if f
            ]

            if not changed_files:
                logger.info("no changed files for %s; skipping re-index", repo_url)
                return

            repo_root = Path(tmpdir)
            embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
            vectorstore = Chroma(
                collection_name=col_name,
                embedding_function=embeddings,
                persist_directory="/data/chroma",
            )

            for rel_path in changed_files:
                abs_path = repo_root / rel_path

                # Delete existing documents for this file
                existing = vectorstore.get(where={"source": rel_path})
                if existing["ids"]:
                    vectorstore.delete(ids=existing["ids"])

                # Re-index if file still exists and is indexable
                if abs_path.exists() and _should_index(abs_path):
                    language = EXTENSION_TO_LANGUAGE.get(abs_path.suffix)
                    if language is None:
                        continue
                    splitter = RecursiveCharacterTextSplitter.from_language(
                        language=language,
                        chunk_size=1000,
                        chunk_overlap=200,
                    )
                    content = abs_path.read_text(encoding="utf-8", errors="ignore")
                    chunks = splitter.create_documents(
                        texts=[content],
                        metadatas=[{"source": rel_path}],
                    )
                    vectorstore.add_documents(chunks)

            logger.info(
                "incremental re-index complete: repo=%s files_updated=%d",
                repo_url, len(changed_files),
            )

        await _update_metadata(repo_url, head_sha, status="ready")
```

### Fallback to Full Re-index

| Condition | Action |
|-----------|--------|
| `base_sha` not in shallow clone (force push, rebase) | Full `build_codebase_index` |
| Diff returns non-zero exit code | Full `build_codebase_index` |
| Changed file list is empty | Skip (no-op) |
| File deleted in push | Documents deleted from Chroma; not re-added |

---

## 8. Known Limitations

### Repository Size Limit

Maximum repository size: **500 MB** (checked via `du` before clone).

```python
def _check_repo_size(repo_url: str):
    """Raises ValueError if the remote repository is too large to index."""
    # GitHub API: GET /repos/{owner}/{repo} returns "size" in KB
    import httpx
    path = repo_url.replace("https://github.com/", "")  # "owner/repo"
    resp = httpx.get(
        f"https://api.github.com/repos/{path}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
    )
    resp.raise_for_status()
    size_mb = resp.json()["size"] / 1024
    if size_mb > MAX_REPO_SIZE_MB:
        raise ValueError(
            f"Repository {repo_url} is {size_mb:.0f} MB, "
            f"exceeding the {MAX_REPO_SIZE_MB} MB limit."
        )
```

### Private Repositories

Private repositories require `GITHUB_TOKEN` with `repo` scope. The token is injected via the
`GITHUB_TOKEN` environment variable in the `agentops-arq-worker` container. Public repositories
work without authentication but the token is still sent (GitHub ignores it for public repos).

### Concurrent Write Protection

The Chroma collection is not thread-safe for concurrent writes. The ARQ worker acquires a
per-repo Redis lock before any index build or update:

```python
lock_key = f"index_lock:{collection_name(repo_url)}"
async with redis.lock(lock_key, timeout=3600):
    ...
```

- Lock timeout: 3600 seconds (1 hour). If a build takes longer, the lock expires and a new build
  can start — acceptable because Chroma's worst case is a partially-updated collection, not
  corruption.
- The `agentops-codebase-search` service only reads from Chroma. Read/write isolation at the
  Chroma level is not needed, only write/write isolation.

### Index Staleness

An index older than 24 hours triggers a background rebuild before the next job (see Section 6,
enqueue conditions). Between the job submission and the rebuild completing, the search agent uses
the stale index. This is acceptable — stale code embeddings are better than no embeddings.

If the index is in `status = 'building'` when a search is requested, `get_codebase_retriever`
still returns the existing (stale) collection rather than failing. The new build will complete
in the background and future searches will use the updated index.
