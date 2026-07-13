from pathlib import Path

from app.runtime.paths import AppPaths


def test_discover_respects_explicit_development_paths(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "test-data"
    frontend_dir = tmp_path / "web"
    monkeypatch.setenv("SEMIREVIEW_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SEMIREVIEW_FRONTEND_DIST", str(frontend_dir))

    paths = AppPaths.discover(frozen=False, project_root=tmp_path / "project")

    assert paths.data == data_dir.resolve()
    assert paths.frontend_dist == frontend_dir.resolve()


def test_frozen_app_uses_local_app_data_and_bundled_frontend(monkeypatch, tmp_path: Path):
    local_app_data = tmp_path / "Local"
    bundle = tmp_path / "bundle"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("SEMIREVIEW_DATA_DIR", raising=False)
    monkeypatch.delenv("SEMIREVIEW_FRONTEND_DIST", raising=False)

    paths = AppPaths.discover(frozen=True, resource_root=bundle)

    assert paths.root == (local_app_data / "SemiconductorReview").resolve()
    assert paths.data == (paths.root / "Data")
    assert paths.backups == (paths.root / "Backups")
    assert paths.logs == (paths.root / "Logs")
    assert paths.runtime == (paths.root / "Runtime")
    assert paths.frontend_dist == (bundle / "frontend" / "dist").resolve()


def test_ensure_directories_creates_persistent_directories(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = AppPaths.discover(frozen=True, resource_root=tmp_path / "bundle")

    paths.ensure_directories()

    assert all(path.is_dir() for path in (paths.data, paths.backups, paths.logs, paths.runtime))
