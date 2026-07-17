import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from app.shared.errors import AppError
from app.runtime.identity import DATABASE_NAME
from app.runtime.migrations import migrate_database

BACKUP_FORMAT_VERSION = 2
BACKUP_PRODUCT = "shiyao"
_FORMAL_DATA_DIRECTORIES = {"sources", "uploads"}


class InvalidBackupError(AppError):
    def __init__(self, message: str = "The backup archive is invalid."):
        super().__init__(code="INVALID_BACKUP", message=message, status_code=422)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_archive_name(name: str) -> bool:
    if "\\" in name or ":" in name:
        return False
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _data_files(data_dir: Path) -> list[Path]:
    files = [data_dir / DATABASE_NAME]
    for directory in _FORMAL_DATA_DIRECTORIES:
        root = data_dir / directory
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(path for path in files if path.is_file())


def _sanitize_database_snapshot(path: Path) -> None:
    if not path.is_file():
        return
    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "durable_job" in tables:
            connection.execute(
                "UPDATE durable_job SET worker_id = NULL, lease_expires_at = NULL, "
                "last_heartbeat_at = NULL"
            )
        if "ai_provider_profile" in tables:
            connection.execute("UPDATE ai_provider_profile SET models_fetched_at = NULL")
        connection.commit()


def create_backup(data_dir: Path, app_version: str = "0.2.1") -> bytes:
    files = _data_files(data_dir)
    contents: dict[str, bytes] = {}
    database_path = data_dir / DATABASE_NAME
    with tempfile.TemporaryDirectory(prefix="shiyao-backup-") as temp:
        snapshot_path = Path(temp) / DATABASE_NAME
        if database_path.is_file():
            with (
                closing(sqlite3.connect(database_path)) as source,
                closing(sqlite3.connect(snapshot_path)) as destination,
            ):
                source.backup(destination)
                destination.commit()
            _sanitize_database_snapshot(snapshot_path)
        for path in files:
            relative = path.relative_to(data_dir).as_posix()
            contents[relative] = (
                snapshot_path.read_bytes()
                if path == database_path and snapshot_path.is_file()
                else path.read_bytes()
            )
    manifest = {
        "format_version": BACKUP_FORMAT_VERSION,
        "product": BACKUP_PRODUCT,
        "app_version": app_version,
        "created_at": datetime.now(UTC).isoformat(),
        "counts": {"files": len(contents)},
        "contains_secrets": False,
        "checksums": {name: _sha256(content) for name, content in contents.items()},
    }
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, content in contents.items():
            archive.writestr(f"data/{name}", content)
    return output.getvalue()


def validate_backup(content: bytes) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise InvalidBackupError("The backup contains duplicate paths.")
            if not all(_safe_archive_name(name) for name in names):
                raise InvalidBackupError("The backup contains unsafe paths.")
            if "manifest.json" not in names:
                raise InvalidBackupError("The backup manifest is missing.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
                errors.append("Unsupported backup format version.")
            if manifest.get("product") != BACKUP_PRODUCT:
                errors.append("Backup product does not match Shiyao.")
            if manifest.get("contains_secrets") is not False:
                errors.append("Backup must not contain secrets.")
            checksums = manifest.get("checksums", {})
            if not isinstance(checksums, dict):
                raise InvalidBackupError("The backup checksums are invalid.")
            expected_data_names = {f"data/{name}" for name in checksums}
            actual_data_names = {
                name for name in names if name.startswith("data/") and not name.endswith("/")
            }
            if actual_data_names != expected_data_names:
                errors.append("Backup data files do not match the manifest.")
            if manifest.get("counts", {}).get("files") != len(checksums):
                errors.append("Backup file count does not match the manifest.")
            for name, expected in checksums.items():
                if not _safe_archive_name(name):
                    errors.append(f"Unsafe manifest path: {name}")
                    continue
                archive_name = f"data/{name}"
                if archive_name not in names or _sha256(archive.read(archive_name)) != expected:
                    errors.append(f"Checksum mismatch: {name}")
            return manifest, errors
    except (BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise InvalidBackupError() from error


def restore_backup(content: bytes, data_dir: Path, engine) -> dict:
    manifest, errors = validate_backup(content)
    if errors:
        raise InvalidBackupError("; ".join(errors))
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shiyao-restore-", dir=data_dir.parent) as temp:
        working = Path(temp)
        stage = working / "staged"
        rollback = working / "rollback"
        stage.mkdir()
        rollback.mkdir()
        with ZipFile(BytesIO(content)) as archive:
            for name in archive.namelist():
                if not name.startswith("data/") or name.endswith("/"):
                    continue
                relative = PurePosixPath(name).relative_to("data")
                if (
                    relative.parts[0] != DATABASE_NAME
                    and relative.parts[0] not in _FORMAL_DATA_DIRECTORIES
                ):
                    continue
                target = stage.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        staged_database = stage / DATABASE_NAME
        if not staged_database.is_file():
            raise InvalidBackupError("The backup database is missing.")
        with closing(sqlite3.connect(staged_database)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise InvalidBackupError("The backup database failed integrity validation.")
        engine.dispose()
        formal_targets = [
            data_dir / DATABASE_NAME,
            *(data_dir / name for name in _FORMAL_DATA_DIRECTORIES),
        ]
        try:
            for target in formal_targets:
                if target.exists():
                    shutil.move(str(target), rollback / target.name)
            for source in stage.iterdir():
                shutil.move(str(source), data_dir / source.name)
            migrate_database(data_dir / DATABASE_NAME, data_dir.parent / "Backups")
        except Exception:
            for target in formal_targets:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            for source in rollback.iterdir():
                shutil.move(str(source), data_dir / source.name)
            raise
    return manifest
