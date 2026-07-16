import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.contracts import ProviderResult
from app.providers.credentials import MemorySecretStore
from app.runtime.paths import AppPaths


class PassingAdapter:
    async def list_models(self):
        return []

    async def generate_text(self, request):
        return ProviderResult(value="ok", model_id=request.model)

    async def generate_json(self, request):
        return ProviderResult(value=request.output_type(ok=True, message="ok"), model_id=request.model)


def configured_app(tmp_path: Path):
    paths = AppPaths(
        root=tmp_path,
        data=tmp_path / "Data",
        backups=tmp_path / "Backups",
        logs=tmp_path / "Logs",
        runtime=tmp_path / "Runtime",
        frontend_dist=tmp_path / "frontend" / "dist",
    )
    paths.ensure_directories()
    app = create_app(
        data_dir=paths.data,
        secret_store=MemorySecretStore(),
        provider_adapter_factory=lambda _profile, _key: PassingAdapter(),
    )
    app.state.paths = paths
    app.state.packaged = True
    return app, paths


def test_diagnostics_reports_operations_without_learning_data_or_secrets(tmp_path: Path):
    app, paths = configured_app(tmp_path)
    secret = "unique-canary-key-731946"
    private_phrase = "private-course-phrase-829104"
    (paths.logs / "app.log").write_text(
        f"Authorization: Bearer {secret}\nrequest failed safely\n",
        encoding="utf-8",
    )
    (paths.data / "private-source.txt").write_text(private_phrase, encoding="utf-8")
    (paths.runtime / "parse-cache").mkdir(exist_ok=True)
    (paths.runtime / "parse-cache" / "entry").write_bytes(b"parse")
    (paths.runtime / "ai-cache").mkdir()
    (paths.runtime / "ai-cache" / "entry").write_bytes(b"ai")

    with TestClient(app) as client:
        provider = client.post("/api/providers", json={
            "name": "主力服务", "protocol": "openai_compatible",
            "base_url": "https://relay.example/v1", "api_key": secret,
        }).json()
        model = client.post(f"/api/providers/{provider['id']}/models", json={
            "model_id": "review-model", "display_name": "Review Model",
        }).json()
        client.post(f"/api/providers/{provider['id']}/models/{model['id']}:probe")
        response = client.get("/api/system/diagnostics")

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        assert "summary.json" in archive.namelist()
        combined = b"".join(archive.read(name) for name in archive.namelist())
        summary = json.loads(archive.read("summary.json"))
    assert summary["providers"][0]["host"] == "relay.example"
    assert summary["providers"][0]["protocol"] == "openai_compatible"
    assert summary["providers"][0]["models"][0]["structured_status"] == "passed"
    assert summary["cache"]["parse"] == {"files": 1, "bytes": 5}
    assert secret.encode() not in combined
    assert private_phrase.encode() not in combined
    assert b"request failed safely" in combined


def test_cache_clear_requires_exact_size_and_preserves_formal_data(tmp_path: Path):
    app, paths = configured_app(tmp_path)
    parse = paths.runtime / "parse-cache"
    parse.mkdir(exist_ok=True)
    (parse / "entry").write_bytes(b"123456")
    formal = paths.data / "formal.txt"
    formal.write_text("keep", encoding="utf-8")

    with TestClient(app) as client:
        stats = client.get("/api/system/caches").json()
        rejected = client.post("/api/system/caches/parse/clear", json={
            "expected_bytes": stats["parse"]["bytes"], "confirmation": "CLEAR 0",
        })
        cleared = client.post("/api/system/caches/parse/clear", json={
            "expected_bytes": 6, "confirmation": "CLEAR 6",
        })

    assert rejected.status_code == 409
    assert cleared.status_code == 200
    assert cleared.json()["removed"] == {"files": 1, "bytes": 6}
    assert list(parse.iterdir()) == []
    assert formal.read_text(encoding="utf-8") == "keep"
