from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.runtime.identity import APPLICATION_DATA_DIR_NAME


@dataclass(frozen=True)
class AppPaths:
    root: Path
    data: Path
    backups: Path
    logs: Path
    runtime: Path
    frontend_dist: Path

    @classmethod
    def discover(
        cls,
        *,
        frozen: bool | None = None,
        project_root: Path | None = None,
        resource_root: Path | None = None,
    ) -> "AppPaths":
        is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        source_root = (project_root or Path(__file__).resolve().parents[3]).resolve()
        if resource_root is None:
            if is_frozen:
                resource_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            else:
                resource_root = source_root
        resources = Path(resource_root).resolve()

        if is_frozen:
            local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            root = Path(
                os.environ.get("SHIYAO_ROOT", local_app_data / APPLICATION_DATA_DIR_NAME)
            ).resolve()
            default_data = root / "Data"
        else:
            root = Path(os.environ.get("SHIYAO_ROOT", source_root)).resolve()
            default_data = source_root / "data"

        data = Path(os.environ.get("SHIYAO_DATA_DIR", default_data)).resolve()
        frontend = Path(
            os.environ.get("SHIYAO_FRONTEND_DIST", resources / "frontend" / "dist")
        ).resolve()
        return cls(
            root=root,
            data=data,
            backups=(root / "Backups").resolve(),
            logs=(root / "Logs").resolve(),
            runtime=(root / "Runtime").resolve(),
            frontend_dist=frontend,
        )

    def ensure_directories(self) -> None:
        for path in (self.data, self.backups, self.logs, self.runtime):
            path.mkdir(parents=True, exist_ok=True)
