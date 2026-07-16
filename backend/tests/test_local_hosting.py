import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_ready_cors_security_headers_and_spa_hosting(tmp_path: Path):
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<main>本地复习台</main>", encoding="utf-8")
    app = create_app(data_dir=tmp_path / "data", frontend_dist_dir=frontend)

    with TestClient(app) as client:
        ready = client.get("/ready")
        page = client.get("/")
        preflight = client.options(
            "/api/projects",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert ready.status_code == 200
    assert ready.json()["application"] == "shiyao-review"
    assert ready.json()["protocol_version"] == 2
    assert ready.json()["checks"]["database"] == "ok"
    assert "本地复习台" in page.text
    assert page.headers["x-content-type-options"] == "nosniff"
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_application_shutdown_disposes_the_sqlite_engine(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data")
    original_dispose = app.state.database.dispose
    disposed = False

    def tracked_dispose():
        nonlocal disposed
        disposed = True
        original_dispose()

    app.state.database.dispose = tracked_dispose
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200

    assert disposed is True


def test_local_runner_honors_the_graceful_stop_file(tmp_path: Path, monkeypatch):
    from app import runner

    stop_file = tmp_path / "stop.signal"
    stop_file.write_text("stop", encoding="utf-8")
    seen: dict[str, bool] = {}

    class FakeServer:
        def __init__(self, _config):
            self.should_exit = False

        def run(self):
            deadline = time.monotonic() + 1
            while not self.should_exit and time.monotonic() < deadline:
                time.sleep(0.01)
            seen["stopped"] = self.should_exit

    monkeypatch.setenv("SHIYAO_STOP_FILE", str(stop_file))
    monkeypatch.setattr(runner, "create_default_app", lambda: object())
    monkeypatch.setattr(runner.uvicorn, "Config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner.uvicorn, "Server", FakeServer)

    runner.main()

    assert seen["stopped"] is True
    assert not stop_file.exists()
