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
from app.desktop.windows_session import WindowsSessionMonitor
from app.main import create_app
from app.runtime.migrations import migrate_database
from app.runtime.paths import AppPaths
from app.system.service import configure_file_logging, is_setup_complete


def process_is_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import win32api
    import win32process

    try:
        handle = win32api.OpenProcess(0x1000, False, pid)
    except Exception:
        return False
    try:
        return win32process.GetExitCodeProcess(handle) == 259
    finally:
        win32api.CloseHandle(handle)


def wait_for_process_exit(
    pid: int,
    *,
    process_running: Callable[[int], bool] = process_is_running,
    timeout: float = 20,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    deadline = time.monotonic() + max(timeout, 0)
    while process_running(pid):
        if time.monotonic() >= deadline:
            return False
        sleep(0.1)
    return True


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
        first_run = not is_setup_complete(resolved_paths.data)
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
        session_monitor = WindowsSessionMonitor(app.state.shutdown_callback)
        session_monitor.start()
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
            session_monitor.close()
            store.remove_if_owned_by(os.getpid())
            browser_thread.join(timeout=1)
        return 0
    finally:
        mutex.close()


def shutdown_existing(paths: AppPaths | None = None) -> int:
    resolved_paths = paths or AppPaths.discover()
    store = InstanceStore(resolved_paths.runtime)
    metadata = store.read()
    if metadata is None:
        return 0
    if not validate_instance(metadata):
        if process_is_running(metadata.pid):
            return 1
        store.remove_if_owned_by(metadata.pid)
        return 0
    try:
        request = Request(f"{metadata.base_url}/api/system/shutdown", method="POST")
        with urlopen(request, timeout=3) as response:
            if response.status not in (200, 202, 204):
                return 1
        return 0 if wait_for_process_exit(metadata.pid) else 1
    except OSError:
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--shutdown", action="store_true")
    arguments, _unknown = parser.parse_known_args()
    return shutdown_existing() if arguments.shutdown else launch()


if __name__ == "__main__":
    raise SystemExit(main())
