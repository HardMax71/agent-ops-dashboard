import hashlib

import chromadb
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from agentops.config import get_settings


def collection_name(repo_url: str) -> str:
    """Normalize URL and return a stable collection name."""
    normalised = repo_url.rstrip("/").removesuffix(".git")
    return f"repo_{hashlib.sha256(normalised.encode()).hexdigest()[:16]}"


def get_codebase_retriever(repository: str):  # noqa: ANN201
    """Get a Chroma retriever for the given repository.

    Validates that the collection exists before returning a retriever.
    Returns None if the collection does not exist yet.
    """
    settings = get_settings()
    col_name = collection_name(repository)

    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    client.get_collection(col_name)  # Raises InvalidCollectionException if not found

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma(
        collection_name=col_name,
        embedding_function=embeddings,
        persist_directory=settings.chroma_persist_dir,
        client=client,
    )
    return vectorstore.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 8, "score_threshold": 0.3},
    )
