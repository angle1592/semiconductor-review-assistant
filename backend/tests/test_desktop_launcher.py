from pathlib import Path

from app.desktop.instance import InstanceMetadata, InstanceStore
from app.desktop.launcher import launch, shutdown_existing, wait_for_process_exit
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
    assert opened == ["http://127.0.0.1:54322/setup"]
    assert InstanceStore(paths.runtime).read() is None
    assert mutex.closed


def test_completed_setup_opens_dashboard_on_new_process(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.ensure_directories()
    (paths.data / ".setup-complete").write_text("complete", encoding="ascii")
    server = FakeServer()
    opened: list[str] = []

    result = launch(
        paths,
        mutex_factory=lambda: FakeMutex(acquired=True),
        server_factory=lambda _app, _port: server,
        browser_open=opened.append,
        validator=lambda _metadata: True,
        port_picker=lambda: 54323,
    )

    assert result == 0
    assert opened == ["http://127.0.0.1:54323/"]


def test_shutdown_waits_for_service_process_to_exit():
    states = iter([True, True, False])
    sleeps: list[float] = []

    stopped = wait_for_process_exit(
        1234,
        process_running=lambda _pid: next(states),
        timeout=1,
        sleep=lambda seconds: sleeps.append(seconds),
    )

    assert stopped is True
    assert sleeps == [0.1, 0.1]


def test_shutdown_refuses_success_for_unhealthy_running_instance(tmp_path: Path, monkeypatch):
    paths = _paths(tmp_path)
    paths.ensure_directories()
    InstanceStore(paths.runtime).write(InstanceMetadata(pid=4321, port=54324))
    monkeypatch.setattr("app.desktop.launcher.validate_instance", lambda _metadata: False)
    monkeypatch.setattr("app.desktop.launcher.process_is_running", lambda _pid: True)

    assert shutdown_existing(paths) == 1


def test_shutdown_cleans_stale_unhealthy_instance_metadata(tmp_path: Path, monkeypatch):
    paths = _paths(tmp_path)
    paths.ensure_directories()
    InstanceStore(paths.runtime).write(InstanceMetadata(pid=4322, port=54325))
    monkeypatch.setattr("app.desktop.launcher.validate_instance", lambda _metadata: False)
    monkeypatch.setattr("app.desktop.launcher.process_is_running", lambda _pid: False)

    assert shutdown_existing(paths) == 0
    assert InstanceStore(paths.runtime).read() is None
