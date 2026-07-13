from __future__ import annotations

import io
import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.desktop.instance import APPLICATION_ID, PROTOCOL_VERSION
from app.runtime.version import APPLICATION_VERSION


LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOG_EXPORT_LIMIT = 512 * 1024


def configure_file_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    root = logging.getLogger()
    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename).resolve() == log_path.resolve()
        for handler in root.handlers
    ):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    return log_path


def open_directory(path: Path, opener=None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if opener is not None:
        opener(path)
        return
    os.startfile(path)  # type: ignore[attr-defined]


def _sanitize(text: str) -> str:
    sanitized = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+",
        r"\1[REDACTED]",
        text,
    )
    sanitized = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", sanitized)
    home = str(Path.home())
    if home:
        sanitized = sanitized.replace(home, "%USERPROFILE%")
    return sanitized


def create_diagnostics(paths, *, packaged: bool, settings: dict) -> bytes:
    system = {
        "application": APPLICATION_ID,
        "version": APPLICATION_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "packaged": packaged,
        "data_directory": str(paths.data),
        "log_directory": str(paths.logs),
        "provider": settings.get("provider"),
        "base_url": settings.get("base_url"),
        "model": settings.get("model"),
        "vision_enabled": settings.get("vision_enabled"),
        "api_key_configured": bool(settings.get("api_key_configured")),
    }
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "system.json",
            _sanitize(json.dumps(system, ensure_ascii=False, indent=2)),
        )
        for log_path in sorted(paths.logs.glob("app.log*")):
            if not log_path.is_file():
                continue
            content = log_path.read_bytes()[-LOG_EXPORT_LIMIT:].decode("utf-8", errors="replace")
            archive.writestr(f"logs/{log_path.name}", _sanitize(content))
    return stream.getvalue()
