import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.main import create_app


def test_app_registers_project_routes_and_no_legacy_domain_routes(tmp_path: Path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/projects", json={"name": "综合复习"}).status_code == 201
        assert client.get("/api/courses").status_code == 404
        assert client.get("/api/lessons/missing").status_code == 404
        assert client.get("/api/review/due").status_code == 404


def test_backup_export_validate_and_restore_excludes_secrets(tmp_path: Path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        client.post("/api/projects", json={"name": "可靠性"})
        runtime_pid = tmp_path / "runtime" / "server.pid"
        runtime_pid.parent.mkdir(parents=True)
        runtime_pid.write_text("12345", encoding="ascii")
        exported = client.get("/api/backups/export")
        assert exported.status_code == 200
        archive = exported.content

        with ZipFile(BytesIO(archive)) as bundle:
            names = bundle.namelist()
            assert "manifest.json" in names
            assert "data/runtime/server.pid" not in names
            assert not any("api_key" in name.lower() or "secret" in name.lower() for name in names)

        validated = client.post(
            "/api/backups/validate",
            files={"file": ("backup.zip", archive, "application/zip")},
        )
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        assert validated.json()["manifest"]["contains_secrets"] is False

        tampered_stream = BytesIO(archive)
        with ZipFile(tampered_stream, "a") as bundle:
            bundle.writestr("data/unlisted.txt", b"not in manifest")
        tampered = client.post(
            "/api/backups/validate",
            files={"file": ("tampered.zip", tampered_stream.getvalue(), "application/zip")},
        )
        assert tampered.status_code == 200
        assert tampered.json()["valid"] is False

        legacy_runtime = b"pid from an older backup"
        with ZipFile(BytesIO(archive)) as source:
            legacy_entries = {name: source.read(name) for name in source.namelist()}
        legacy_manifest = json.loads(legacy_entries["manifest.json"])
        legacy_manifest["counts"]["files"] += 1
        legacy_manifest["checksums"]["runtime/server.pid"] = hashlib.sha256(
            legacy_runtime
        ).hexdigest()
        legacy_entries["manifest.json"] = json.dumps(legacy_manifest).encode()
        legacy_stream = BytesIO()
        with ZipFile(legacy_stream, "w", ZIP_DEFLATED) as legacy_bundle:
            for name, content in legacy_entries.items():
                legacy_bundle.writestr(name, content)
            legacy_bundle.writestr("data/runtime/server.pid", legacy_runtime)

        stale = tmp_path / "uploads" / "stale" / "old.bin"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"created after backup")
        runtime_pid.write_text("67890", encoding="ascii")

        restored = client.post(
            "/api/backups/restore",
            files={"file": ("backup.zip", legacy_stream.getvalue(), "application/zip")},
        )
        assert restored.status_code == 200
        assert restored.json()["restored"] is True
        assert restored.json()["requires_restart"] is True
        assert not stale.exists()
        assert runtime_pid.read_text(encoding="ascii") == "67890"
