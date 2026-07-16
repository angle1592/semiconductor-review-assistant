import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.providers.contracts import ProviderResult, RemoteModel, StructuredRequest, TextRequest
from app.providers.endpoints import ResolvedEndpoints
from app.providers.errors import invalid_response_error, map_http_error, map_transport_error


class AnthropicAdapter:
    def __init__(self, endpoints: ResolvedEndpoints, api_key: str, client: httpx.AsyncClient | None = None):
        self.endpoints = endpoints
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=60)

    @property
    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

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
            return [RemoteModel(id=item["id"], display_name=item.get("display_name") or item["id"]) for item in response.json()["data"]]
        except (KeyError, TypeError, ValueError) as error:
            raise invalid_response_error() from error

    def _content(self, prompt: str, images: list[str]) -> list[dict]:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for image in images:
            try:
                header, data = image.split(",", 1)
                media_type = header.split(";")[0].removeprefix("data:")
            except ValueError as error:
                raise ValueError("Image must be a base64 data URL") from error
            content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
        return content

    async def _complete(self, model: str, prompt: str, system: str, images: list[str]) -> tuple[str, httpx.Response, dict]:
        payload: dict[str, Any] = {"model": model, "max_tokens": 2048, "messages": [{"role": "user", "content": self._content(prompt, images)}]}
        if system:
            payload["system"] = system
        response = await self._send(self.endpoints.inference_url, payload=payload)
        try:
            body = response.json()
            text = next(item["text"] for item in body["content"] if item.get("type") == "text")
            return text, response, body.get("usage", {})
        except (KeyError, StopIteration, TypeError, ValueError) as error:
            raise invalid_response_error() from error

    def _result(self, value, model: str, response: httpx.Response, usage: dict) -> ProviderResult:
        return ProviderResult(value=value, model_id=model, input_tokens=int(usage.get("input_tokens", 0)), output_tokens=int(usage.get("output_tokens", 0)), cached_input_tokens=int(usage.get("cache_read_input_tokens", 0)), cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens", 0)), request_id=response.headers.get("request-id"))

    async def generate_text(self, request: TextRequest) -> ProviderResult[str]:
        text, response, usage = await self._complete(request.model, request.prompt, request.system, request.images)
        return self._result(text, request.model, response, usage)

    async def probe_prompt_cache(self, model: str) -> ProviderResult[str]:
        payload = {
            "model": model,
            "max_tokens": 8,
            "cache_control": {"type": "ephemeral"},
            "messages": [{"role": "user", "content": [{"type": "text", "text": "只回答 OK。"}]}],
        }
        response = await self._send(self.endpoints.inference_url, payload=payload)
        try:
            body = response.json()
            text = next(item["text"] for item in body["content"] if item.get("type") == "text")
            return self._result(text, model, response, body.get("usage", {}))
        except (KeyError, StopIteration, TypeError, ValueError) as error:
            raise invalid_response_error() from error

    async def generate_json(self, request: StructuredRequest[Any]) -> ProviderResult[Any]:
        schema = request.output_type.model_json_schema()
        prompt = f"{request.prompt}\n只返回符合此 JSON Schema 的 JSON：{json.dumps(schema, ensure_ascii=False)}"
        raw, response, usage = await self._complete(request.model, prompt, request.system, request.images)
        try:
            value = request.output_type.model_validate_json(raw)
        except (ValidationError, ValueError, json.JSONDecodeError):
            repair = f"修复为严格符合此 JSON Schema 的 JSON，只返回 JSON。\nSchema: {json.dumps(schema, ensure_ascii=False)}\n原输出: {raw}"
            raw, response, usage = await self._complete(request.model, repair, request.system, [])
            try:
                value = request.output_type.model_validate_json(raw)
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                raise invalid_response_error() from error
        return self._result(value, request.model, response, usage)
