from pathlib import Path

from app.desktop.instance import InstanceMetadata, InstanceStore
from app.desktop.launcher import launch
from app.runtime.paths import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        root=tmp_path,
        data=tmp_path / "Data",
        backups=tmp_path / "Backups",
        logs=tmp_path / "Logs",
        runtime=tmp_path / "Runtime",
        frontend_dist=tmp_path / "frontend" / "dist",
    )


class FakeMutex:
    def __init__(self, acquired: bool):
        self.acquired = acquired
        self.closed = False

    def acquire(self) -> bool:
        return self.acquired

    def close(self) -> None:
        self.closed = True


class FakeServer:
    def __init__(self):
        self.should_exit = False
        self.ran = False

    def run(self) -> None:
        self.ran = True


def test_second_launch_opens_verified_existing_instance(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.ensure_directories()
    metadata = InstanceMetadata(pid=99, port=54321)
    InstanceStore(paths.runtime).write(metadata)
    opened: list[str] = []
    mutex = FakeMutex(acquired=False)

    result = launch(
        paths,
        mutex_factory=lambda: mutex,
        browser_open=opened.append,
        validator=lambda current: current == metadata,
        wait_timeout=0,
    )

    assert result == 0
    assert opened == ["http://127.0.0.1:54321/"]
    assert mutex.closed


def test_first_launch_runs_server_and_cleans_runtime_metadata(tmp_path: Path):
    paths = _paths(tmp_path)
    server = FakeServer()
    opened: list[str] = []
    mutex = FakeMutex(acquired=True)

    result = launch(
        paths,
        mutex_factory=lambda: mutex,
        server_factory=lambda _app, _port: server,
        browser_open=opened.append,
        validator=lambda _metadata: True,
        port_picker=lambda: 54322,
    )

    assert result == 0
    assert server.ran
    assert opened == ["http://127.0.0.1:54322/"]
    assert InstanceStore(paths.runtime).read() is None
    assert mutex.closed
