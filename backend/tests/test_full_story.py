import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest

from app.main import create_app
from app.providers.anthropic import AnthropicAdapter
from app.providers.credentials import MemorySecretStore
from app.providers.endpoints import resolve_endpoints
from app.providers.openai_compatible import OpenAICompatibleAdapter


def test_phase_one_review_project_story(tmp_path: Path):
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        ready = client.get('/ready')
        created = client.post(
            '/api/projects',
            json={
                'name': '资格考试总复习',
                'description': '汇总多份考试资料',
                'importance_prompt': '优先定义、公式与易错点',
            },
        )
        project_id = created.json()['id']
        listed = client.get('/api/projects')
        deleted = client.delete(f'/api/projects/{project_id}')
        after_delete = client.get('/api/projects')

    assert ready.status_code == 200
    assert ready.json()['checks']['database'] == 'ok'
    assert created.status_code == 201
    assert [project['id'] for project in listed.json()] == [project_id]
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["sources"] == 0
    assert after_delete.json() == []


@pytest.mark.parametrize("protocol", ["openai_compatible", "anthropic"])
def test_provider_setup_story_uses_real_adapters_with_mocked_upstream(tmp_path: Path, protocol: str):
    upstream_requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else None
        upstream_requests.append({"method": request.method, "path": request.url.path, "payload": payload})
        if request.method == "GET" and request.url.path == "/v1/models":
            model = {"id": f"{protocol}-review-model", "display_name": "Review Model"}
            return httpx.Response(200, json={"data": [model], "has_more": False})
        if request.method == "POST" and request.url.path in {"/v1/chat/completions", "/v1/messages"}:
            if protocol == "openai_compatible":
                structured = "response_format" in payload
                content = '{"ok":true,"message":"ready"}' if structured else "OK"
                return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {}})
            prompt = payload["messages"][0]["content"][0]["text"]
            content = '{"ok":true,"message":"ready"}' if "JSON Schema" in prompt else "OK"
            return httpx.Response(200, json={"content": [{"type": "text", "text": content}], "usage": {}})
        raise AssertionError(f"Unexpected upstream request: {request.method} {request.url}")

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def adapter_factory(profile, api_key):
        endpoints = resolve_endpoints(profile.protocol, profile.base_url)
        if profile.protocol == "anthropic":
            return AnthropicAdapter(endpoints, api_key, upstream)
        return OpenAICompatibleAdapter(endpoints, api_key, upstream)

    app = create_app(
        data_dir=tmp_path,
        secret_store=MemorySecretStore(),
        provider_adapter_factory=adapter_factory,
    )

    try:
        with TestClient(app) as client:
            client.post(
                "/api/projects",
                json={
                    "name": "私人资料关键词-绝不发送",
                    "description": "仅保存在项目数据库中",
                    "importance_prompt": "优先复习私人资料关键词",
                },
            )
            provider = client.post(
                "/api/providers",
                json={
                    "name": f"{protocol} test",
                    "protocol": protocol,
                    "base_url": "https://provider.test",
                    "api_key": "private-test-key",
                },
            ).json()
            models = client.post(f"/api/providers/{provider['id']}/models:refresh").json()
            blocked = client.post(f"/api/providers/{provider['id']}:enable")
            probed = client.post(f"/api/providers/{provider['id']}/models/{models[0]['id']}:probe").json()
            enabled = client.post(f"/api/providers/{provider['id']}:enable").json()
            completed = client.post("/api/system/setup-complete")
            system_info = client.get("/api/system/info").json()
    finally:
        asyncio.run(upstream.aclose())

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "provider_not_validated"
    assert probed["text_status"] == "passed"
    assert probed["structured_status"] == "passed"
    assert probed["vision_status"] == "passed"
    assert enabled["enabled"] is True
    assert enabled["is_default"] is True
    assert completed.status_code == 204
    assert system_info["setup_complete"] is True
    assert any(request["path"] == "/v1/models" for request in upstream_requests)
    assert "私人资料关键词" not in json.dumps(upstream_requests, ensure_ascii=False)
