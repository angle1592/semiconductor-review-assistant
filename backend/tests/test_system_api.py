from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.ai.secrets import MemorySecretStore
from app.main import create_app
from app.runtime.paths import AppPaths


def _configured_app(tmp_path: Path):
    paths = AppPaths(
        root=tmp_path,
        data=tmp_path / "Data",
        backups=tmp_path / "Backups",
        logs=tmp_path / "Logs",
        runtime=tmp_path / "Runtime",
        frontend_dist=tmp_path / "frontend" / "dist",
    )
    paths.ensure_directories()
    app = create_app(data_dir=paths.data, secret_store=MemorySecretStore())
    app.state.paths = paths
    app.state.packaged = True
    return app, paths


def test_system_info_reports_first_run_state_without_exposing_secrets(tmp_path: Path):
    app, paths = _configured_app(tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/system/info")

    assert response.status_code == 200
    assert response.json() == {
        "application": "semiconductor-review-assistant",
        "version": "0.1.0-beta",
        "packaged": True,
        "setup_complete": False,
        "data_directory": str(paths.data),
        "log_directory": str(paths.logs),
    }


def test_open_path_only_accepts_allowlisted_directories(tmp_path: Path):
    app, paths = _configured_app(tmp_path)
    opened: list[Path] = []
    app.state.path_opener = opened.append

    with TestClient(app) as client:
        allowed = client.post("/api/system/paths/logs/open")
        rejected = client.post("/api/system/paths/secrets/open")

    assert allowed.status_code == 204
    assert opened == [paths.logs]
    assert rejected.status_code == 404


def test_diagnostics_archive_is_sanitized_and_excludes_learning_data(tmp_path: Path):
    app, paths = _configured_app(tmp_path)
    (paths.logs / "app.log").write_text(
        "Authorization: Bearer sk-example-secret-value\nrequest failed",
        encoding="utf-8",
    )
    (paths.data / "private-course.pdf").write_bytes(b"private learning material")

    with TestClient(app) as client:
        response = client.get("/api/system/diagnostics")

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        names = archive.namelist()
        combined = b"".join(archive.read(name) for name in names)
    assert "system.json" in names
    assert "logs/app.log" in names
    assert not any("private-course" in name for name in names)
    assert b"sk-example-secret-value" not in combined
    assert b"private learning material" not in combined


def test_shutdown_uses_registered_callback(tmp_path: Path):
    app, _paths = _configured_app(tmp_path)
    stopped: list[bool] = []
    app.state.shutdown_callback = lambda: stopped.append(True)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/system/shutdown")

    assert response.status_code == 202
    assert stopped == [True]
