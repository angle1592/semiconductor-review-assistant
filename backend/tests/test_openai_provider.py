import httpx
import pytest
from pydantic import BaseModel

from app.providers.contracts import StructuredRequest
from app.providers.endpoints import resolve_endpoints
from app.providers.openai_compatible import OpenAICompatibleAdapter


class ProbeOutput(BaseModel):
    ok: bool


@pytest.mark.asyncio
async def test_openai_lists_models_with_bearer_key():
    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"data": [{"id": "vision-model", "owned_by": "test"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(resolve_endpoints("openai_compatible", "https://host.test"), "sk-test", client)
    assert [model.id for model in await adapter.list_models()] == ["vision-model"]
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_generates_structured_result_and_usage():
    async def handler(request: httpx.Request):
        payload = __import__("json").loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        return httpx.Response(200, headers={"x-request-id": "req-1"}, json={"choices": [{"message": {"content": '{"ok":true}'}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": 4}}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(resolve_endpoints("openai_compatible", "https://host.test"), "sk-test", client)
    result = await adapter.generate_json(StructuredRequest(model="model-a", prompt="probe", output_type=ProbeOutput))
    assert result.value.ok is True
    assert result.input_tokens == 12
    assert result.cached_input_tokens == 4
    assert result.request_id == "req-1"
    await client.aclose()
