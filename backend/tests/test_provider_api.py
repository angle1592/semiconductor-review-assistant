from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.contracts import ProviderResult, RemoteModel
from app.providers.credentials import MemorySecretStore
from app.providers.errors import ProviderError


class FakeAdapter:
    def __init__(self, *, models_error: ProviderError | None = None):
        self.models_error = models_error

    async def list_models(self):
        if self.models_error:
            raise self.models_error
        return [RemoteModel(id="vision-model", display_name="Vision Model")]

    async def generate_text(self, request):
        return ProviderResult(value="ok", model_id=request.model)

    async def generate_json(self, request):
        return ProviderResult(value=request.output_type(ok=True, message="ok"), model_id=request.model)

    async def probe_prompt_cache(self, model):
        return ProviderResult(value="ok", model_id=model, cached_input_tokens=1)


def _client(tmp_path: Path, adapter: FakeAdapter) -> TestClient:
    app = create_app(
        tmp_path / "data",
        secret_store=MemorySecretStore(),
        provider_adapter_factory=lambda _profile, _key: adapter,
    )
    return TestClient(app)


def _create_provider(client: TestClient, protocol: str = "openai_compatible") -> dict:
    response = client.post(
        "/api/providers",
        json={"name": "主力服务", "protocol": protocol, "base_url": "https://relay.test", "api_key": "secret"},
    )
    assert response.status_code == 201
    return response.json()


def test_unsupported_model_list_allows_manual_model(tmp_path: Path):
    adapter = FakeAdapter(models_error=ProviderError(code="upstream_endpoint_not_found", message="手动填写模型。", status_code=422))
    with _client(tmp_path, adapter) as client:
        provider = _create_provider(client)
        fetched = client.post(f"/api/providers/{provider['id']}/models:refresh")
        assert fetched.status_code == 422
        assert fetched.json()["title"] == "upstream_endpoint_not_found"
        manual = client.post(f"/api/providers/{provider['id']}/models", json={"model_id": "relay-model", "display_name": "relay-model"})
        assert manual.status_code == 201


def test_provider_cannot_enable_until_required_probes_pass(tmp_path: Path):
    with _client(tmp_path, FakeAdapter()) as client:
        provider = _create_provider(client)
        model = client.post(f"/api/providers/{provider['id']}/models", json={"model_id": "model-a", "display_name": "Model A"}).json()
        response = client.post(f"/api/providers/{provider['id']}:enable")
        assert response.status_code == 409
        assert response.json()["title"] == "provider_not_validated"

        probed = client.post(f"/api/providers/{provider['id']}/models/{model['id']}:probe")
        assert probed.status_code == 200
        assert probed.json()["vision_status"] == "passed"
        enabled = client.post(f"/api/providers/{provider['id']}:enable")
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True
        assert enabled.json()["is_default"] is True


def test_model_refresh_is_cached_for_fifteen_minutes(tmp_path: Path):
    adapter = FakeAdapter()
    calls = 0
    original = adapter.list_models

    async def counted():
        nonlocal calls
        calls += 1
        return await original()

    adapter.list_models = counted
    with _client(tmp_path, adapter) as client:
        provider = _create_provider(client)
        first = client.post(f"/api/providers/{provider['id']}/models:refresh")
        second = client.post(f"/api/providers/{provider['id']}/models:refresh")
        forced = client.post(f"/api/providers/{provider['id']}/models:refresh?force=true")
    assert first.status_code == second.status_code == forced.status_code == 200
    assert calls == 2
