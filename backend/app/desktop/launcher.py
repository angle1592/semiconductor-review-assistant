from __future__ import annotations

import argparse
import os
import threading
import time
import webbrowser
from collections.abc import Callable
from urllib.request import Request, urlopen

import uvicorn

from app.desktop.instance import (
    InstanceMetadata,
    InstanceStore,
    WindowsUserMutex,
    find_free_port,
    validate_instance,
)
from app.main import create_app
from app.runtime.migrations import migrate_database
from app.runtime.paths import AppPaths
from app.system.service import configure_file_logging


def _server_factory(app, port: int):
    return uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False)
    )


def _wait_for_instance(
    store: InstanceStore,
    validator: Callable[[InstanceMetadata], bool],
    timeout: float,
) -> InstanceMetadata | None:
    deadline = time.monotonic() + max(timeout, 0)
    while True:
        metadata = store.read()
        if metadata is not None and validator(metadata):
            return metadata
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.1)


def launch(
    paths: AppPaths | None = None,
    *,
    mutex_factory: Callable[[], object] = WindowsUserMutex,
    server_factory: Callable = _server_factory,
    browser_open: Callable[[str], object] = webbrowser.open,
    validator: Callable[[InstanceMetadata], bool] = validate_instance,
    port_picker: Callable[[], int] = find_free_port,
    wait_timeout: float = 15,
) -> int:
    resolved_paths = paths or AppPaths.discover()
    resolved_paths.ensure_directories()
    configure_file_logging(resolved_paths.logs)
    store = InstanceStore(resolved_paths.runtime)
    mutex = mutex_factory()
    acquired = mutex.acquire()
    try:
        if not acquired:
            existing = _wait_for_instance(store, validator, wait_timeout)
            if existing is None:
                return 2
            browser_open(f"{existing.base_url}/")
            return 0

        database_path = resolved_paths.data / "review.db"
        first_run = not database_path.exists()
        migrate_database(database_path, resolved_paths.backups)
        app = create_app(
            data_dir=resolved_paths.data,
            frontend_dist_dir=resolved_paths.frontend_dist,
        )
        app.state.paths = resolved_paths
        app.state.packaged = bool(getattr(__import__("sys"), "frozen", False))
        port = port_picker()
        metadata = InstanceMetadata(pid=os.getpid(), port=port)
        server = server_factory(app, port)
        app.state.shutdown_callback = lambda: setattr(server, "should_exit", True)
        store.write(metadata)

        def open_when_ready() -> None:
            ready = _wait_for_instance(store, validator, wait_timeout)
            if ready is not None:
                browser_open(f"{ready.base_url}/setup" if first_run else f"{ready.base_url}/")

        browser_thread = threading.Thread(target=open_when_ready, daemon=True)
        browser_thread.start()
        try:
            server.run()
        finally:
            store.remove_if_owned_by(os.getpid())
            browser_thread.join(timeout=1)
        return 0
    finally:
        mutex.close()


def shutdown_existing(paths: AppPaths | None = None) -> int:
    resolved_paths = paths or AppPaths.discover()
    metadata = InstanceStore(resolved_paths.runtime).read()
    if metadata is None or not validate_instance(metadata):
        return 0
    try:
        request = Request(f"{metadata.base_url}/api/system/shutdown", method="POST")
        with urlopen(request, timeout=3) as response:
            return 0 if response.status in (200, 202, 204) else 1
    except OSError:
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--shutdown", action="store_true")
    arguments, _unknown = parser.parse_known_args()
    return shutdown_existing() if arguments.shutdown else launch()


if __name__ == "__main__":
    raise SystemExit(main())
