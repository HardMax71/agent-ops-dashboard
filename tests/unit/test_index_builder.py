from pathlib import Path

from agentops.index.builder import INDEXED_EXTENSIONS, _chunk_repository, _should_index


def test_should_index_python_file(tmp_path: Path) -> None:
    py_file = tmp_path / "test.py"
    py_file.write_text("def hello():\n    pass\n")
    assert _should_index(py_file) is True


def test_should_not_index_binary_file(tmp_path: Path) -> None:
    bin_file = tmp_path / "test.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09")
    assert _should_index(bin_file) is False


def test_should_not_index_unknown_extension(tmp_path: Path) -> None:
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("hello world")
    assert _should_index(txt_file) is False


def test_chunk_repository(tmp_path: Path) -> None:
    py_file = tmp_path / "main.py"
    py_file.write_text("def hello():\n    return 'hello'\n\ndef world():\n    return 'world'\n")

    docs = _chunk_repository(tmp_path)
    assert len(docs) > 0
    assert all(isinstance(d, dict) for d in docs)
    assert all("content" in d and "metadata" in d for d in docs)


def test_indexed_extensions() -> None:
    assert ".py" in INDEXED_EXTENSIONS
    assert ".js" in INDEXED_EXTENSIONS
    assert ".ts" in INDEXED_EXTENSIONS
    assert ".go" in INDEXED_EXTENSIONS
    assert ".java" in INDEXED_EXTENSIONS
    assert ".txt" not in INDEXED_EXTENSIONS


def test_chunk_repository_skips_git_dir(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_file = git_dir / "config.py"
    git_file.write_text("# git internal")

    normal_file = tmp_path / "app.py"
    normal_file.write_text("def app(): pass")

    docs = _chunk_repository(tmp_path)
    sources = [d["metadata"]["source"] for d in docs]
    assert all(".git" not in s for s in sources)
