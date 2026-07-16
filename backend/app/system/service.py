from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
SETUP_MARKER_NAME = ".setup-complete"


def setup_marker(data_dir: Path) -> Path:
    return data_dir / SETUP_MARKER_NAME


def is_setup_complete(data_dir: Path) -> bool:
    return setup_marker(data_dir).is_file()


def mark_setup_complete(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    setup_marker(data_dir).write_text("complete\n", encoding="ascii")


def invalidate_setup(data_dir: Path) -> None:
    setup_marker(data_dir).unlink(missing_ok=True)


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
