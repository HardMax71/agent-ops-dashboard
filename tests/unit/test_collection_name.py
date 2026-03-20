from agentops.index.collection import collection_name


def test_collection_name_stable() -> None:
    name1 = collection_name("https://github.com/owner/repo")
    name2 = collection_name("https://github.com/owner/repo")
    assert name1 == name2


def test_collection_name_normalizes_trailing_slash() -> None:
    name1 = collection_name("https://github.com/owner/repo")
    name2 = collection_name("https://github.com/owner/repo/")
    assert name1 == name2


def test_collection_name_normalizes_git_suffix() -> None:
    name1 = collection_name("https://github.com/owner/repo")
    name2 = collection_name("https://github.com/owner/repo.git")
    assert name1 == name2


def test_collection_name_format() -> None:
    name = collection_name("https://github.com/owner/repo")
    assert name.startswith("repo_")
    assert len(name) == 5 + 16  # "repo_" + 16 hex chars


def test_different_repos_different_names() -> None:
    name1 = collection_name("https://github.com/owner/repo1")
    name2 = collection_name("https://github.com/owner/repo2")
    assert name1 != name2
