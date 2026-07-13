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

_EXCLUDED_DATA_DIRECTORIES = {"backups", "restore-staged", "codex-provider", "runtime"}


class InvalidBackupError(AppError):
    def __init__(self, message: str = "The backup archive is invalid."):
        super().__init__(message, "INVALID_BACKUP", 422)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_archive_name(name: str) -> bool:
    if "\\" in name or ":" in name:
        return False
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _data_files(data_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in data_dir.rglob("*")
        if path.is_file()
        and not _EXCLUDED_DATA_DIRECTORIES.intersection(path.relative_to(data_dir).parts)
        and not path.name.endswith(("-wal", "-shm", "-journal"))
    )


def create_backup(data_dir: Path, app_version: str = "0.1.0") -> bytes:
    files = _data_files(data_dir)
    contents: dict[str, bytes] = {}
    database_path = data_dir / "review.db"
    with tempfile.TemporaryDirectory(prefix="semiconductor-backup-") as temp:
        snapshot_path = Path(temp) / "review.db"
        if database_path.is_file():
            with (
                closing(sqlite3.connect(database_path)) as source,
                closing(sqlite3.connect(snapshot_path)) as destination,
            ):
                source.backup(destination)
                destination.commit()
        for path in files:
            relative = path.relative_to(data_dir).as_posix()
            contents[relative] = (
                snapshot_path.read_bytes()
                if path == database_path and snapshot_path.is_file()
                else path.read_bytes()
            )
    manifest = {
        "format_version": 1,
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
            if manifest.get("format_version") != 1:
                errors.append("Unsupported backup format version.")
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
    with tempfile.TemporaryDirectory(prefix="semiconductor-restore-", dir=data_dir.parent) as temp:
        stage = Path(temp)
        with ZipFile(BytesIO(content)) as archive:
            for name in archive.namelist():
                if not name.startswith("data/") or name.endswith("/"):
                    continue
                relative = PurePosixPath(name).relative_to("data")
                if _EXCLUDED_DATA_DIRECTORIES.intersection(relative.parts):
                    continue
                target = stage.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        engine.dispose()
        for existing in _data_files(data_dir):
            existing.unlink(missing_ok=True)
        for source in stage.rglob("*"):
            if not source.is_file():
                continue
            target = data_dir / source.relative_to(stage)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for directory in sorted(
            (path for path in data_dir.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if directory.name not in _EXCLUDED_DATA_DIRECTORIES:
                try:
                    directory.rmdir()
                except OSError:
                    pass
    return manifest
