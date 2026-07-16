from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.runtime.identity import APPLICATION_ID, DATABASE_NAME, PROTOCOL_VERSION
from app.runtime.version import APPLICATION_VERSION

LOG_EXPORT_LIMIT = 512 * 1024
CACHE_DIRECTORIES = {"parse": "parse-cache", "ai": "ai-cache"}


def directory_stats(path: Path) -> dict[str, int]:
    if not path.is_dir():
        return {"files": 0, "bytes": 0}
    files = [item for item in path.rglob("*") if item.is_file()]
    return {"files": len(files), "bytes": sum(item.stat().st_size for item in files)}


def cache_summary(paths) -> dict[str, dict[str, int]]:
    return {
        kind: directory_stats(paths.runtime / directory)
        for kind, directory in CACHE_DIRECTORIES.items()
    }


def clear_cache(paths, kind: str, *, expected_bytes: int, confirmation: str) -> dict[str, int]:
    directory = CACHE_DIRECTORIES.get(kind)
    if directory is None:
        raise ValueError("unknown cache")
    target = (paths.runtime / directory).resolve()
    target.relative_to(paths.runtime.resolve())
    current = directory_stats(target)
    if expected_bytes != current["bytes"] or confirmation != f"CLEAR {current['bytes']}":
        raise ValueError("cache changed or confirmation does not match")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return current


def redact_text(text: str, known_secrets: tuple[str, ...] = ()) -> str:
    sanitized = text
    for secret in sorted((value for value in known_secrets if value), key=len, reverse=True):
        sanitized = sanitized.replace(secret, "[REDACTED]")
    patterns = (
        (r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+", r"\1[REDACTED]"),
        (r"(?i)((?:x-api-key|api[_-]?key|x-goog-api-key)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]"),
        (r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|secret)=)[^&\s\"']+", r"\1[REDACTED]"),
        (r"(?i)(https?://)[^/@\s]+@", r"\1[REDACTED]@"),
        (r"(?i)([\"'](?:api[_-]?key|access[_-]?token|token|secret|password)[\"']\s*:\s*[\"'])[^\"']+", r"\1[REDACTED]"),
        (r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]"),
    )
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    home = str(Path.home())
    return sanitized.replace(home, "%USERPROFILE%") if home else sanitized


def _database_summary(database_path: Path) -> dict:
    result = {"tasks": {}, "recent_public_error_codes": {}}
    if not database_path.is_file():
        return result
    with closing(sqlite3.connect(database_path)) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "durable_job" in tables:
            result["tasks"] = {
                status: count
                for status, count in connection.execute(
                    "SELECT status, COUNT(*) FROM durable_job GROUP BY status"
                )
            }
        codes: list[str] = []
        for table in ("durable_job", "analysis_run", "analysis_batch", "generated_artifact"):
            if table not in tables:
                continue
            codes.extend(
                row[0]
                for row in connection.execute(
                    f"SELECT public_error_code FROM {table} "
                    "WHERE public_error_code IS NOT NULL ORDER BY updated_at DESC LIMIT 20"
                )
            )
        result["recent_public_error_codes"] = dict(Counter(codes).most_common(20))
    return result


def create_diagnostics(
    paths,
    *,
    packaged: bool,
    provider_summary: dict,
    known_secrets: tuple[str, ...] = (),
) -> bytes:
    summary = {
        "application": APPLICATION_ID,
        "version": APPLICATION_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "packaged": packaged,
        "install_method": "windows-installer" if packaged else "source",
        "windows_version": platform.platform(),
        "paths": {
            "data_writable": os.access(paths.data, os.W_OK),
            "runtime_writable": os.access(paths.runtime, os.W_OK),
            "logs_writable": os.access(paths.logs, os.W_OK),
        },
        "providers": provider_summary.get("providers", []),
        "cache": cache_summary(paths),
        **_database_summary(paths.data / DATABASE_NAME),
    }
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "summary.json",
            redact_text(json.dumps(summary, ensure_ascii=False, indent=2), known_secrets),
        )
        for log_path in sorted(paths.logs.glob("app.log*")):
            if not log_path.is_file():
                continue
            content = log_path.read_bytes()[-LOG_EXPORT_LIMIT:].decode("utf-8", errors="replace")
            archive.writestr(
                f"logs/{log_path.name}",
                redact_text(content, known_secrets),
            )
    return stream.getvalue()
