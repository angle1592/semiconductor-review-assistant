import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.providers.contracts import ProviderResult, RemoteModel, StructuredRequest, TextRequest
from app.providers.endpoints import ResolvedEndpoints
from app.providers.errors import invalid_response_error, map_http_error, map_transport_error


def _close_json_schema_objects(value: Any) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            value.setdefault("additionalProperties", False)
        for child in value.values():
            _close_json_schema_objects(child)
    elif isinstance(value, list):
        for child in value:
            _close_json_schema_objects(child)


class OpenAICompatibleAdapter:
    def __init__(self, endpoints: ResolvedEndpoints, api_key: str, client: httpx.AsyncClient | None = None):
        self.endpoints = endpoints
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=60)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _send(self, url: str, *, method: str = "POST", payload: dict | None = None) -> httpx.Response:
        try:
            response = await self.client.request(method, url, headers=self.headers, json=payload, timeout=60)
        except httpx.HTTPError as error:
            raise map_transport_error(error) from error
        if not response.is_success:
            raise map_http_error(response)
        return response

    async def list_models(self) -> list[RemoteModel]:
        response = await self._send(self.endpoints.models_url, method="GET")
        try:
            return [RemoteModel(id=item["id"], display_name=item.get("name") or item["id"]) for item in response.json()["data"]]
        except (KeyError, TypeError, ValueError) as error:
            raise invalid_response_error() from error

    def _content(self, prompt: str, images: list[str], prompt_prefix: str = "") -> str | list[dict]:
        combined = f"{prompt_prefix}{prompt}"
        if not images:
            return combined
        return [{"type": "text", "text": combined}, *({"type": "image_url", "image_url": {"url": image}} for image in images)]

    async def _complete(self, model: str, prompt: str, system: str, images: list[str], schema: dict | None = None, *, prompt_prefix: str = "", temperature: float = 0) -> tuple[str, httpx.Response, dict]:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": self._content(prompt, images, prompt_prefix)})
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "shiyao_result", "strict": True, "schema": schema}}
        response = await self._send(self.endpoints.inference_url, payload=payload)
        try:
            body = response.json()
            return body["choices"][0]["message"]["content"], response, body.get("usage", {})
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise invalid_response_error() from error

    def _result(self, value, model: str, response: httpx.Response, usage: dict) -> ProviderResult:
        details = usage.get("prompt_tokens_details")
        reported = isinstance(details, dict) and "cached_tokens" in details
        return ProviderResult(value=value, model_id=model, input_tokens=int(usage.get("prompt_tokens", 0)), output_tokens=int(usage.get("completion_tokens", 0)), cached_input_tokens=int((details or {}).get("cached_tokens", 0)), cache_usage_reported=reported, request_id=response.headers.get("x-request-id"))

    async def generate_text(self, request: TextRequest) -> ProviderResult[str]:
        text, response, usage = await self._complete(request.model, request.prompt, request.system, request.images, prompt_prefix=request.prompt_prefix, temperature=request.temperature)
        return self._result(text, request.model, response, usage)

    async def generate_json(self, request: StructuredRequest[Any]) -> ProviderResult[Any]:
        schema = request.output_type.model_json_schema()
        _close_json_schema_objects(schema)
        raw, response, usage = await self._complete(request.model, request.prompt, request.system, request.images, schema, prompt_prefix=request.prompt_prefix, temperature=request.temperature)
        try:
            value = request.output_type.model_validate_json(raw)
        except (ValidationError, ValueError, json.JSONDecodeError):
            repair = f"修复为严格符合此 JSON Schema 的 JSON，只返回 JSON。\nSchema: {json.dumps(schema, ensure_ascii=False)}\n原输出: {raw}"
            raw, response, usage = await self._complete(request.model, repair, request.system, [], schema, temperature=request.temperature)
            try:
                value = request.output_type.model_validate_json(raw)
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                raise invalid_response_error() from error
        return self._result(value, request.model, response, usage)
