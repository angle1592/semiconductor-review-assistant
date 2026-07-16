import logging
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
        "application": "shiyao-review",
        "version": "0.1.0-beta",
        "packaged": True,
        "setup_complete": False,
        "data_directory": str(paths.data),
        "log_directory": str(paths.logs),
    }


def test_setup_completion_requires_configuration_and_persists_marker(tmp_path: Path):
    app, paths = _configured_app(tmp_path)

    with TestClient(app) as client:
        rejected = client.post("/api/system/setup-complete")
        client.put(
            "/api/settings/ai",
            json={
                "provider": "openai_compatible",
                "base_url": "https://models.example/v1",
                "model": "vision-model",
                "api_key": "test-only-key",
            },
        )
        completed = client.post("/api/system/setup-complete")
        info = client.get("/api/system/info")

    assert rejected.status_code == 409
    assert completed.status_code == 204
    assert (paths.data / ".setup-complete").is_file()
    assert info.json()["setup_complete"] is True


def test_changing_ai_settings_invalidates_setup_marker(tmp_path: Path):
    app, paths = _configured_app(tmp_path)
    marker = paths.data / ".setup-complete"
    marker.write_text("complete", encoding="ascii")

    with TestClient(app) as client:
        client.put(
            "/api/settings/ai",
            json={
                "provider": "openai_compatible",
                "base_url": "https://models.example/v1",
                "model": "new-model",
                "api_key": "replacement-key",
            },
        )
        info = client.get("/api/system/info")

    assert not marker.exists()
    assert info.json()["setup_complete"] is False


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
        "Authorization: Bearer sk-example-secret-value\n"
        "Authorization: Basic dXNlcjpwYXNzd29yZA==\n"
        "x-api-key: private-test-key\n"
        "https://user:password@example.test/v1?api_key=query-secret&safe=yes\n"
        "request failed",
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
    assert b"dXNlcjpwYXNzd29yZA" not in combined
    assert b"private-test-key" not in combined
    assert b"user:password" not in combined
    assert b"query-secret" not in combined
    assert b"private learning material" not in combined


def test_requests_and_unexpected_error_type_are_logged_without_error_message(
    tmp_path: Path, caplog
):
    app, _paths = _configured_app(tmp_path)

    @app.get("/api/test/boom")
    def boom():
        raise RuntimeError("private-payload-must-not-enter-log")

    with caplog.at_level(logging.INFO), TestClient(app, raise_server_exceptions=False) as client:
        healthy = client.get("/health")
        failed = client.get("/api/test/boom")

    assert healthy.status_code == 200
    assert failed.status_code == 500
    assert "path=/health status=200" in caplog.text
    assert "path=/api/test/boom status=500" in caplog.text
    assert "exception=RuntimeError" in caplog.text
    assert "private-payload-must-not-enter-log" not in caplog.text


def test_shutdown_uses_registered_callback(tmp_path: Path):
    app, _paths = _configured_app(tmp_path)
    stopped: list[bool] = []
    app.state.shutdown_callback = lambda: stopped.append(True)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/system/shutdown")

    assert response.status_code == 202
    assert stopped == [True]
