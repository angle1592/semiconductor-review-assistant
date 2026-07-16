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


def test_database_upgrades_through_study_artifact_schemas(tmp_path: Path):
    database_path = tmp_path / "Data" / "shiyao.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO app_metadata (key, value) VALUES ('product', 'shiyao-review')"
        )
        connection.execute("PRAGMA user_version=1")

    migrate_database(database_path, tmp_path / "Backups")

    assert CURRENT_DATABASE_VERSION == 7
    assert _user_version(database_path) == 7
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }

    assert {
        "ai_provider_profile",
        "model_profile",
        "source_document",
        "source_block",
        "durable_job",
        "analysis_run",
        "analysis_batch",
        "keypoint_candidate",
        "keypoint",
        "source_question",
        "generated_artifact",
    } <= tables
    assert {
        "ix_source_document_project_id",
        "ix_source_document_sha256",
        "ix_source_block_document_id",
        "ix_source_block_ordinal",
        "ix_durable_job_status_available_at",
        "ix_analysis_run_project_id",
        "ix_analysis_batch_run_id",
        "ix_keypoint_candidate_run_id",
        "ix_keypoint_project_position",
        "ix_source_question_project_id",
        "ix_generated_artifact_project_kind",
    } <= indexes
