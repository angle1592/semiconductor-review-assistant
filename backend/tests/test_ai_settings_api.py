import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.schemas import ConnectionTestResult, ProviderCapabilities
from app.ai.secrets import MemorySecretStore
from app.main import create_app


class FakeProvider:
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text=True, vision=False, structured_output=True)

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            ok=True,
            available=True,
            message="连接成功",
            capabilities=["text", "structured_output"],
        )

    async def generate_learning_items(self, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    async def assess_answer(self, request):  # pragma: no cover - protocol stub
        raise NotImplementedError


def test_ai_settings_persist_without_leaking_api_key(tmp_path: Path) -> None:
    secrets = MemorySecretStore()
    selected: list[tuple[str, str | None]] = []

    def factory(settings, api_key, _data_dir):
        selected.append((settings.provider, api_key))
        return FakeProvider()

    app = create_app(data_dir=tmp_path, secret_store=secrets, ai_provider_factory=factory)
    with TestClient(app) as client:
        initial = client.get("/api/settings/ai")
        saved = client.put(
            "/api/settings/ai",
            json={
                "provider": "openai_compatible",
                "base_url": "https://models.example/v1",
                "model": "review-vision",
                "vision_enabled": True,
                "api_key": "super-secret-api-key",
            },
        )
        fetched = client.get("/api/settings/ai")
        tested = client.post(
            "/api/settings/ai/test",
            json={
                "provider": "openai_compatible",
                "base_url": "https://models.example/v1",
                "model": "review-model",
                "vision_enabled": False,
            },
        )

    assert initial.status_code == 200
    assert initial.json()["api_key_configured"] is False
    assert saved.status_code == 200
    assert saved.json()["api_key_configured"] is True
    assert "api_key" not in saved.json()
    assert "super-secret-api-key" not in saved.text
    assert fetched.json()["base_url"] == "https://models.example/v1"
    assert tested.status_code == 200
    assert tested.json()["capabilities"] == ["text", "structured_output"]
    assert selected == [("openai_compatible", "super-secret-api-key")]
    assert secrets.get("openai_compatible_api_key") == "super-secret-api-key"

    with sqlite3.connect(tmp_path / "shiyao.db") as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(ai_settings)").fetchall()
        }
    assert "api_key" not in columns
    assert "super-secret-api-key".encode() not in (tmp_path / "shiyao.db").read_bytes()


def test_ai_test_uses_unsaved_key_without_persisting_it(tmp_path: Path) -> None:
    secrets = MemorySecretStore()
    seen_keys: list[str | None] = []

    def factory(_settings, api_key, _data_dir):
        seen_keys.append(api_key)
        return FakeProvider()

    app = create_app(data_dir=tmp_path, secret_store=secrets, ai_provider_factory=factory)
    with TestClient(app) as client:
        response = client.post(
            "/api/settings/ai/test",
            json={
                "provider": "openai_compatible",
                "base_url": "https://models.example/v1",
                "model": "model",
                "api_key": "temporary-key",
            },
        )

    assert response.status_code == 200
    assert seen_keys == ["temporary-key"]
    assert secrets.get("openai_compatible_api_key") is None
    assert "temporary-key" not in response.text
