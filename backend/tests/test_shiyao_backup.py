import json
import sqlite3
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import app.backup.service as backup_service
from app.backup.service import InvalidBackupError, create_backup, restore_backup, validate_backup
from app.shared.database import create_database


def test_v2_backup_contains_only_formal_data_and_scrubs_runtime_state(tmp_path: Path):
    data = tmp_path / "Data"
    engine = create_database(data)
    source = data / "sources" / "project-1" / "asset"
    source.mkdir(parents=True)
    (source / "source.pdf").write_bytes(b"original source")
    (source / "assets").mkdir()
    (source / "assets" / "page.png").write_bytes(b"preview")
    for excluded in ("Runtime/parse-cache", "Runtime/ai-cache", "Logs", "Backups", "provider-runtime"):
        path = data / excluded
        path.mkdir(parents=True)
        (path / "private.bin").write_bytes(b"must not be exported")
    with sqlite3.connect(data / "shiyao.db") as connection:
        connection.execute(
            "INSERT INTO durable_job (kind,payload_json,status,attempts,max_attempts,available_at,"
            "worker_id,lease_expires_at,last_heartbeat_at,created_at,updated_at) "
            "VALUES ('analysis','{}','running',0,3,'2026-01-01','worker-secret',"
            "'2026-01-01','2026-01-01','2026-01-01','2026-01-01')"
        )
        connection.commit()

    content = create_backup(data)
    with ZipFile(BytesIO(content)) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        snapshot = tmp_path / "snapshot.db"
        snapshot.write_bytes(archive.read("data/shiyao.db"))

    assert manifest["format_version"] == 2
    assert manifest["product"] == "shiyao"
    assert set(names) == {
        "manifest.json",
        "data/shiyao.db",
        "data/sources/project-1/asset/source.pdf",
        "data/sources/project-1/asset/assets/page.png",
    }
    with sqlite3.connect(snapshot) as connection:
        lease = connection.execute(
            "SELECT worker_id, lease_expires_at, last_heartbeat_at FROM durable_job"
        ).fetchone()
    assert lease == (None, None, None)
    engine.dispose()


def test_backup_validation_rejects_tampering_secrets_and_unsafe_paths(tmp_path: Path):
    data = tmp_path / "Data"
    engine = create_database(data)
    valid = create_backup(data)

    tampered = rewrite_archive(valid, replace_data={"data/shiyao.db": b"not the database"})
    _, errors = validate_backup(tampered)
    assert any("Checksum mismatch" in error for error in errors)

    claimed_secrets = rewrite_archive(valid, manifest_updates={"contains_secrets": True})
    _, errors = validate_backup(claimed_secrets)
    assert "Backup must not contain secrets." in errors

    wrong_version = rewrite_archive(valid, manifest_updates={"format_version": 999})
    _, errors = validate_backup(wrong_version)
    assert "Unsupported backup format version." in errors

    with ZipFile(BytesIO(valid)) as archive:
        entries = [(name, archive.read(name)) for name in archive.namelist()]
    unsafe = BytesIO()
    with ZipFile(unsafe, "w", ZIP_DEFLATED) as archive:
        for name, value in entries:
            archive.writestr(name, value)
        archive.writestr("data/../escape.txt", b"escape")
    with pytest.raises(InvalidBackupError, match="unsafe paths"):
        validate_backup(unsafe.getvalue())
    engine.dispose()


def test_restore_rolls_back_formal_data_when_post_swap_migration_fails(tmp_path: Path, monkeypatch):
    source_data = tmp_path / "Source" / "Data"
    source_engine = create_database(source_data)
    (source_data / "sources" / "new").mkdir(parents=True)
    (source_data / "sources" / "new" / "source.txt").write_text("new", encoding="utf-8")
    archive = create_backup(source_data)

    target_data = tmp_path / "Target" / "Data"
    target_engine = create_database(target_data)
    (target_data / "sources" / "old").mkdir(parents=True)
    old_file = target_data / "sources" / "old" / "source.txt"
    old_file.write_text("old", encoding="utf-8")
    monkeypatch.setattr(backup_service, "migrate_database", lambda *_args: (_ for _ in ()).throw(RuntimeError("migration failed")))

    with pytest.raises(RuntimeError, match="migration failed"):
        restore_backup(archive, target_data, target_engine)

    assert old_file.read_text(encoding="utf-8") == "old"
    assert not (target_data / "sources" / "new").exists()
    source_engine.dispose()
    target_engine.dispose()


def rewrite_archive(content: bytes, *, manifest_updates=None, replace_data=None) -> bytes:
    manifest_updates = manifest_updates or {}
    replace_data = replace_data or {}
    output = BytesIO()
    with ZipFile(BytesIO(content)) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        manifest = json.loads(source.read("manifest.json"))
        manifest.update(manifest_updates)
        for name in source.namelist():
            if name == "manifest.json":
                target.writestr(name, json.dumps(manifest))
            else:
                target.writestr(name, replace_data.get(name, source.read(name)))
    return output.getvalue()
