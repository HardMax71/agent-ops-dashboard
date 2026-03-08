from pathlib import Path

import chardet
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

INDEXED_EXTENSIONS: set[str] = {".py", ".js", ".ts", ".go", ".java"}

EXTENSION_TO_LANGUAGE: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".ts": Language.TS,
    ".go": Language.GO,
    ".java": Language.JAVA,
}


def _should_index(path: Path) -> bool:
    """Return True if file should be indexed (text file with known extension)."""
    if path.suffix not in INDEXED_EXTENSIONS:
        return False
    raw = path.read_bytes()
    if len(raw) == 0:
        return False
    # Binary detection via chardet
    detected = chardet.detect(raw[:8192])
    confidence = detected.get("confidence") or 0.0
    return confidence >= 0.9


def _chunk_repository(repo_dir: Path) -> list[dict]:
    """Walk repo and chunk all indexable files."""
    documents = []
    for file_path in repo_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if ".git" in file_path.parts:
            continue
        if not _should_index(file_path):
            continue

        language = EXTENSION_TO_LANGUAGE[file_path.suffix]
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=language,
            chunk_size=1000,
            chunk_overlap=200,
        )
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        chunks = splitter.split_text(content)
        rel_path = str(file_path.relative_to(repo_dir))
        for idx, chunk in enumerate(chunks):
            documents.append({
                "content": chunk,
                "metadata": {
                    "source": rel_path,
                    "chunk_index": idx,
                    "language": language.value,
                },
            })
    return documents
