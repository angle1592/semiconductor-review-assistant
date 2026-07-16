import sqlite3
from pathlib import Path

import pytest

from app.runtime.migrations import CURRENT_DATABASE_VERSION, migrate_database


def _user_version(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def test_existing_unmarked_database_is_rejected_without_backup(tmp_path: Path):
    database_path = tmp_path / "Data" / "legacy.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE lessons (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO lessons VALUES ('kept')")

    with pytest.raises(RuntimeError, match="not a Shiyao database"):
        migrate_database(database_path, tmp_path / "Backups")

    assert list((tmp_path / "Backups").glob("pre-migration-*.db")) == []
    assert _user_version(database_path) == 0


def test_new_database_does_not_create_backup(tmp_path: Path):
    database_path = tmp_path / "Data" / "shiyao.db"

    backup = migrate_database(database_path, tmp_path / "Backups")

    assert backup is None
    assert _user_version(database_path) == CURRENT_DATABASE_VERSION
    assert list((tmp_path / "Backups").glob("pre-migration-*.db")) == []
    with sqlite3.connect(database_path) as connection:
        marker = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'product'"
        ).fetchone()
    assert marker == ("shiyao-review",)


def test_current_shiyao_database_is_idempotent(tmp_path: Path):
    database_path = tmp_path / "Data" / "shiyao.db"
    migrate_database(database_path, tmp_path / "Backups")
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE kept (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO kept VALUES ('yes')")

    backup = migrate_database(database_path, tmp_path / "Backups")

    assert backup is None
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT id FROM kept").fetchone() == ("yes",)
