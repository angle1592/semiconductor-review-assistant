import httpx
import pytest

from app.providers.anthropic import AnthropicAdapter
from app.providers.contracts import TextRequest
from app.providers.endpoints import resolve_endpoints


@pytest.mark.asyncio
async def test_anthropic_lists_models_with_native_headers():
    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/models"
        assert request.headers["x-api-key"] == "sk-ant-test"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json={"data": [{"id": "claude-test", "display_name": "Claude Test"}], "has_more": False})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicAdapter(resolve_endpoints("anthropic", "https://host.test"), "sk-ant-test", client)
    models = await adapter.list_models()
    assert [(model.id, model.display_name) for model in models] == [("claude-test", "Claude Test")]
    await client.aclose()


@pytest.mark.asyncio
async def test_anthropic_reports_cache_usage():
    async def handler(request: httpx.Request):
        return httpx.Response(200, headers={"request-id": "ant-1"}, json={"content": [{"type": "text", "text": "ready"}], "usage": {"input_tokens": 5, "output_tokens": 1, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 2}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicAdapter(resolve_endpoints("anthropic", "https://host.test"), "sk-ant-test", client)
    result = await adapter.generate_text(TextRequest(model="claude-test", prompt="ping"))
    assert result.value == "ready"
    assert result.cached_input_tokens == 3
    assert result.cache_creation_input_tokens == 2
    assert result.cache_usage_reported is True
    await client.aclose()
