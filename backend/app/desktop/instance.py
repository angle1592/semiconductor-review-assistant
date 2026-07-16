from __future__ import annotations

import getpass
import json
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

from app.runtime.identity import APPLICATION_ID, PROTOCOL_VERSION


@dataclass(frozen=True)
class InstanceMetadata:
    pid: int
    port: int
    application: str = APPLICATION_ID
    protocol_version: int = PROTOCOL_VERSION

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class InstanceStore:
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self.path = runtime_dir / "instance.json"

    def write(self, metadata: InstanceMetadata) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(metadata), ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.path)

    def read(self) -> InstanceMetadata | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            metadata = InstanceMetadata(
                pid=int(payload["pid"]),
                port=int(payload["port"]),
                application=str(payload["application"]),
                protocol_version=int(payload["protocol_version"]),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None
        if metadata.application != APPLICATION_ID or metadata.protocol_version != PROTOCOL_VERSION:
            return None
        if not 0 < metadata.port < 65536 or metadata.pid <= 0:
            return None
        return metadata

    def remove_if_owned_by(self, pid: int) -> None:
        metadata = self.read()
        if metadata is not None and metadata.pid == pid:
            self.path.unlink(missing_ok=True)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _fetch_json(url: str) -> dict:
    with urlopen(url, timeout=0.8) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_instance(
    metadata: InstanceMetadata,
    *,
    fetch_json: Callable[[str], dict] = _fetch_json,
) -> bool:
    try:
        payload = fetch_json(f"{metadata.base_url}/ready")
    except Exception:
        return False
    return (
        payload.get("application") == APPLICATION_ID
        and payload.get("protocol_version") == PROTOCOL_VERSION
        and payload.get("status") == "ok"
    )


class WindowsUserMutex:
    def __init__(self):
        import win32api
        import win32event

        self._win32api = win32api
        self._win32event = win32event
        safe_user = "".join(character if character.isalnum() else "-" for character in getpass.getuser())
        self._name = f"Local\\Shiyao-{safe_user}"
        self._handle = None

    def acquire(self) -> bool:
        import winerror

        self._handle = self._win32event.CreateMutex(None, True, self._name)
        return self._win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self._handle is not None:
            self._win32api.CloseHandle(self._handle)
            self._handle = None
