import pytest
from persistence import RuntimeStateRepository, VersionConflict, SessionClosed


def test_version_conflict(tmp_path):
    repo = RuntimeStateRepository(tmp_path / "db.sqlite")

    repo.create_initial("rid", "hash", {"v": 1})

    repo.insert_new_version("rid", 1, "hash", {"v": 2})

    with pytest.raises(VersionConflict):
        repo.insert_new_version("rid", 1, "hash", {"v": 3})


def test_session_closure(tmp_path):
    repo = RuntimeStateRepository(tmp_path / "db.sqlite")

    repo.create_initial("rid", "hash", {"v": 1})

    repo.close_session("rid", 1)

    with pytest.raises(SessionClosed):
        repo.get_latest("rid")
