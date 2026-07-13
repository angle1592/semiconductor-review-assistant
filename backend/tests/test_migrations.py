import sqlite3
from pathlib import Path

from app.runtime.migrations import CURRENT_DATABASE_VERSION, migrate_database


def _user_version(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def test_existing_database_is_backed_up_before_version_change(tmp_path: Path):
    database_path = tmp_path / "Data" / "review.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE lessons (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO lessons VALUES ('kept')")

    backup = migrate_database(database_path, tmp_path / "Backups")

    assert backup is not None and backup.is_file()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT id FROM lessons").fetchone()[0] == "kept"
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 0
    assert _user_version(database_path) == CURRENT_DATABASE_VERSION


def test_new_database_does_not_create_backup(tmp_path: Path):
    database_path = tmp_path / "Data" / "review.db"

    backup = migrate_database(database_path, tmp_path / "Backups")

    assert backup is None
    assert _user_version(database_path) == CURRENT_DATABASE_VERSION
    assert list((tmp_path / "Backups").glob("pre-migration-*.db")) == []


def test_migration_backups_keep_only_five_newest(tmp_path: Path):
    database_path = tmp_path / "Data" / "review.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE lessons (id TEXT PRIMARY KEY)")
    backup_dir = tmp_path / "Backups"
    backup_dir.mkdir()
    for number in range(6):
        old = backup_dir / f"pre-migration-20000101-00000{number}-v0.db"
        old.write_bytes(b"old")

    migrate_database(database_path, backup_dir)

    assert len(list(backup_dir.glob("pre-migration-*.db"))) == 5
