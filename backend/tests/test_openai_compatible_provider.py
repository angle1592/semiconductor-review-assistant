import base64
import json
from pathlib import Path

import httpx
import pytest

from app.ai.errors import (
    AINotConfiguredError,
    InvalidModelOutputError,
    UpstreamAuthFailedError,
    UpstreamTimeoutError,
    VisionRequiredError,
)
from app.ai.openai_compatible import OpenAICompatibleProvider
from app.ai.schemas import (
    AnswerAssessmentRequest,
    LearningGenerationRequest,
    LearningSourcePage,
)


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _items_json() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "topic": "光刻",
                    "question": "光刻的主要目的是什么？",
                    "reference_answer": "把掩膜图形转移到光刻胶。",
                    "explanation": "为后续选择性加工定义图形。",
                    "source_refs": ["lecture.pdf#page=3"],
                }
            ]
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_openai_provider_sends_structured_multimodal_request(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\npage-image")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _completion(_items_json())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            base_url="https://model.example/v1/",
            api_key="secret-token",
            model="vision-model",
            vision_enabled=True,
            client=client,
        )
        result = await provider.generate_learning_items(
            LearningGenerationRequest(
                pages=[
                    LearningSourcePage(
                        source_ref="lecture.pdf#page=3",
                        page_number=3,
                        extracted_text="掩膜图形转移",
                        image_path=image_path,
                    )
                ],
                teacher_emphasis="关注套刻误差",
                item_count=1,
            )
        )

    assert result.items[0].source_refs == ["lecture.pdf#page=3"]
    assert len(captured) == 1
    assert captured[0].url == "https://model.example/v1/chat/completions"
    assert captured[0].headers["authorization"] == "Bearer secret-token"
    payload = json.loads(captured[0].content)
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    image_part = next(
        part for part in payload["messages"][1]["content"] if part["type"] == "image_url"
    )
    encoded = image_part["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(encoded) == image_path.read_bytes()


@pytest.mark.asyncio
async def test_openai_provider_repairs_invalid_model_output_once() -> None:
    responses = iter([_completion("not-json"), _completion(_items_json())])
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return next(responses)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            base_url="https://model.example/v1",
            api_key="key",
            model="text-model",
            vision_enabled=False,
            client=client,
        )
        result = await provider.generate_learning_items(
            LearningGenerationRequest(
                pages=[LearningSourcePage(source_ref="notes#1", page_number=1, extracted_text="PN 结")],
                item_count=1,
            )
        )

    assert len(result.items) == 1
    assert len(requests) == 2
    repair_payload = json.loads(requests[1].content)
    assert "修复" in repair_payload["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_openai_provider_rejects_second_invalid_output() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _completion("still-not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            base_url="https://model.example/v1",
            api_key="key",
            model="text-model",
            vision_enabled=False,
            client=client,
        )
        with pytest.raises(InvalidModelOutputError) as error:
            await provider.generate_learning_items(
                LearningGenerationRequest(
                    pages=[LearningSourcePage(source_ref="notes#1", page_number=1)],
                    item_count=1,
                )
            )

    assert calls == 2
    assert error.value.code == "INVALID_MODEL_OUTPUT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "expected_error"),
    [
        (lambda _request: httpx.Response(401), UpstreamAuthFailedError),
        (
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("late", request=request)),
            UpstreamTimeoutError,
        ),
    ],
)
async def test_openai_provider_maps_auth_and_timeout_errors(handler, expected_error) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            base_url="https://model.example/v1",
            api_key="key",
            model="model",
            vision_enabled=False,
            client=client,
        )
        with pytest.raises(expected_error):
            await provider.assess_answer(
                AnswerAssessmentRequest(
                    question="什么是 PN 结？",
                    reference_answer="P 型与 N 型材料形成的结。",
                    user_answer="两种掺杂材料的交界。",
                )
            )


@pytest.mark.asyncio
async def test_openai_provider_requires_configuration_and_vision(tmp_path: Path) -> None:
    unconfigured = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key=None,
        model="model",
        vision_enabled=True,
    )
    with pytest.raises(AINotConfiguredError):
        await unconfigured.assess_answer(
            AnswerAssessmentRequest(question="q", reference_answer="r", user_answer="a")
        )

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"image")
    text_only = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="key",
        model="model",
        vision_enabled=False,
    )
    with pytest.raises(VisionRequiredError):
        await text_only.generate_learning_items(
            LearningGenerationRequest(
                pages=[
                    LearningSourcePage(
                        source_ref="slide#1", page_number=1, image_path=image_path
                    )
                ],
                item_count=1,
            )
        )
