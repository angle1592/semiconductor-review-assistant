from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.runtime.identity import APPLICATION_ID


CURRENT_DATABASE_VERSION = 8
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


def _migrate_to_v1(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT OR REPLACE INTO app_metadata (key, value) VALUES ('product', ?)",
        (APPLICATION_ID,),
    )


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_provider_profile (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            protocol TEXT NOT NULL,
            base_url TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            credential_generation INTEGER NOT NULL DEFAULT 1,
            models_fetched_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_ai_provider_profile_protocol
            ON ai_provider_profile(protocol);
        CREATE TABLE IF NOT EXISTS model_profile (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL REFERENCES ai_provider_profile(id),
            model_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            text_status TEXT NOT NULL DEFAULT 'untested',
            structured_status TEXT NOT NULL DEFAULT 'untested',
            vision_status TEXT NOT NULL DEFAULT 'untested',
            prompt_cache_status TEXT NOT NULL DEFAULT 'untested',
            safe_error_code TEXT,
            validated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_model_profile_provider_id
            ON model_profile(provider_id);
        """
    )


def _migrate_to_v3(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_document (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            extension TEXT NOT NULL,
            media_type TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            source_kind TEXT NOT NULL DEFAULT 'mixed',
            parse_status TEXT NOT NULL DEFAULT 'queued',
            parser_version TEXT NOT NULL,
            page_count INTEGER,
            parse_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_source_document_project_id
            ON source_document(project_id);
        CREATE INDEX IF NOT EXISTS ix_source_document_sha256
            ON source_document(sha256);
        CREATE TABLE IF NOT EXISTS source_block (
            id TEXT PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES source_document(id),
            ordinal INTEGER NOT NULL,
            locator TEXT NOT NULL,
            kind TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            page_number INTEGER,
            heading_path_json TEXT NOT NULL DEFAULT '[]',
            asset_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_source_block_document_id
            ON source_block(document_id);
        CREATE INDEX IF NOT EXISTS ix_source_block_ordinal
            ON source_block(ordinal);
        """
    )


def _migrate_to_v4(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS durable_job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            available_at TEXT NOT NULL,
            worker_id TEXT,
            lease_expires_at TEXT,
            last_heartbeat_at TEXT,
            public_error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_durable_job_kind ON durable_job(kind);
        CREATE INDEX IF NOT EXISTS ix_durable_job_worker_id ON durable_job(worker_id);
        CREATE INDEX IF NOT EXISTS ix_durable_job_status_available_at
            ON durable_job(status, available_at);
        CREATE TABLE IF NOT EXISTS analysis_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            status TEXT NOT NULL DEFAULT 'queued',
            selected_block_ids_json TEXT NOT NULL,
            prompt_snapshot TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            provider_config_generation INTEGER NOT NULL,
            model_id TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            pipeline_version TEXT NOT NULL,
            total_batches INTEGER NOT NULL DEFAULT 0,
            completed_batches INTEGER NOT NULL DEFAULT 0,
            failed_batches INTEGER NOT NULL DEFAULT 0,
            cancellation_requested INTEGER NOT NULL DEFAULT 0,
            public_error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_analysis_run_project_id ON analysis_run(project_id);
        CREATE TABLE IF NOT EXISTS analysis_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES analysis_run(id),
            ordinal INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            block_ids_json TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            result_json TEXT,
            public_error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_analysis_batch_run_id ON analysis_batch(run_id);
        """
    )


def _migrate_to_v5(connection: sqlite3.Connection) -> None:
    additions = {
        "analysis_run": {
            "provider_protocol": "TEXT NOT NULL DEFAULT ''",
            "provider_base_url": "TEXT NOT NULL DEFAULT ''",
            "parameters_json": "TEXT NOT NULL DEFAULT '{}'",
        },
        "analysis_batch": {
            "cache_status": "TEXT",
            "provider_cached_input_tokens": "INTEGER NOT NULL DEFAULT 0",
            "provider_cache_usage_reported": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    for table, columns in additions.items():
        existing = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_to_v6(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS keypoint_candidate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            run_id INTEGER NOT NULL REFERENCES analysis_run(id),
            batch_id INTEGER NOT NULL REFERENCES analysis_batch(id),
            ordinal INTEGER NOT NULL,
            title TEXT NOT NULL,
            explanation TEXT NOT NULL,
            importance TEXT NOT NULL,
            source_block_ids_json TEXT NOT NULL,
            evidence_quotes_json TEXT NOT NULL,
            rationale TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            user_edited INTEGER NOT NULL DEFAULT 0,
            confirmed_keypoint_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_keypoint_candidate_run_batch_ordinal
            ON keypoint_candidate(run_id, batch_id, ordinal);
        CREATE INDEX IF NOT EXISTS ix_keypoint_candidate_project_id
            ON keypoint_candidate(project_id);
        CREATE INDEX IF NOT EXISTS ix_keypoint_candidate_run_id
            ON keypoint_candidate(run_id);
        CREATE TABLE IF NOT EXISTS keypoint (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            title TEXT NOT NULL,
            explanation TEXT NOT NULL,
            importance TEXT NOT NULL,
            source_block_ids_json TEXT NOT NULL DEFAULT '[]',
            evidence_quotes_json TEXT NOT NULL DEFAULT '[]',
            origin TEXT NOT NULL DEFAULT 'manual',
            run_id INTEGER,
            user_edited INTEGER NOT NULL DEFAULT 0,
            fingerprint TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_keypoint_project_fingerprint
            ON keypoint(project_id, fingerprint);
        CREATE INDEX IF NOT EXISTS ix_keypoint_project_position
            ON keypoint(project_id, position);
        """
    )


def _migrate_to_v7(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            document_id INTEGER NOT NULL REFERENCES source_document(id),
            question_text TEXT NOT NULL,
            answer_text TEXT,
            source_block_ids_json TEXT NOT NULL,
            evidence_quotes_json TEXT NOT NULL DEFAULT '[]',
            fingerprint TEXT NOT NULL,
            user_edited INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            run_id INTEGER REFERENCES analysis_run(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_source_question_document_fingerprint
            ON source_question(document_id, fingerprint);
        CREATE INDEX IF NOT EXISTS ix_source_question_project_id ON source_question(project_id);
        CREATE TABLE IF NOT EXISTS generated_artifact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            payload_json TEXT NOT NULL DEFAULT '{}',
            keypoint_ids_json TEXT NOT NULL,
            source_question_ids_json TEXT NOT NULL DEFAULT '[]',
            provider_id TEXT NOT NULL,
            provider_config_generation INTEGER NOT NULL,
            provider_protocol TEXT NOT NULL,
            provider_base_url TEXT NOT NULL,
            model_id TEXT NOT NULL,
            prompt_snapshot TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            cache_status TEXT,
            public_error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_generated_artifact_project_kind
            ON generated_artifact(project_id, kind);
        """
    )


def _migrate_to_v8(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS study_attempt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            mode TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            response_json TEXT,
            correct INTEGER,
            self_rating TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_study_attempt_project_created
            ON study_attempt(project_id, created_at);
        CREATE TABLE IF NOT EXISTS mastery_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES review_project(id),
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            level TEXT NOT NULL DEFAULT 'unrated',
            last_attempt_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mastery_project_target
            ON mastery_record(project_id, target_type, target_id);
        CREATE INDEX IF NOT EXISTS ix_mastery_project_level
            ON mastery_record(project_id, level);
        """
    )


MIGRATIONS = {
    1: _migrate_to_v1,
    2: _migrate_to_v2,
    3: _migrate_to_v3,
    4: _migrate_to_v4,
    5: _migrate_to_v5,
    6: _migrate_to_v6,
    7: _migrate_to_v7,
    8: _migrate_to_v8,
}


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
        for version in range(current_version + 1, CURRENT_DATABASE_VERSION + 1):
            MIGRATIONS[version](connection)
            connection.execute(f"PRAGMA user_version={version}")
        connection.commit()
    _trim_backups(backup_dir)
    return backup_path
