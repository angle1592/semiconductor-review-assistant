from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.runtime.identity import APPLICATION_ID


CURRENT_DATABASE_VERSION = 1
MIGRATION_BACKUP_LIMIT = 5


def _has_user_tables(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone()
    return row is not None


def _product_marker(connection: sqlite3.Connection) -> str | None:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_metadata'"
    ).fetchone()
    if table is None:
        return None
    row = connection.execute(
        "SELECT value FROM app_metadata WHERE key = 'product'"
    ).fetchone()
    return str(row[0]) if row is not None else None


def _trim_backups(backup_dir: Path) -> None:
    backups = sorted(
        backup_dir.glob("pre-migration-*.db"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for stale in backups[MIGRATION_BACKUP_LIMIT:]:
        stale.unlink(missing_ok=True)


def migrate_database(database_path: Path, backup_dir: Path) -> Path | None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    existed = database_path.is_file()
    with sqlite3.connect(database_path) as connection:
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        has_user_tables = _has_user_tables(connection)
        product_marker = _product_marker(connection)

    if has_user_tables and product_marker != APPLICATION_ID:
        raise RuntimeError("Existing database is not a Shiyao database; legacy migration is disabled.")

    if current_version > CURRENT_DATABASE_VERSION:
        raise RuntimeError(
            f"Database version {current_version} is newer than supported version {CURRENT_DATABASE_VERSION}."
        )
    if current_version == CURRENT_DATABASE_VERSION:
        _trim_backups(backup_dir)
        return None

    backup_path: Path | None = None
    if existed and has_user_tables:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        backup_path = backup_dir / f"pre-migration-{timestamp}-v{current_version}.db"
        shutil.copy2(database_path, backup_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO app_metadata (key, value) VALUES ('product', ?)",
            (APPLICATION_ID,),
        )
        connection.execute(f"PRAGMA user_version={CURRENT_DATABASE_VERSION}")
        connection.commit()
    _trim_backups(backup_dir)
    return backup_path
