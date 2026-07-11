import base64
import json
import mimetypes
from typing import TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.errors import (
    AINotConfiguredError,
    AIProviderError,
    InvalidModelOutputError,
    UpstreamAuthFailedError,
    UpstreamProviderError,
    UpstreamTimeoutError,
    VisionRequiredError,
)
from app.ai.schemas import (
    AnswerAssessment,
    AnswerAssessmentRequest,
    ConnectionTestResult,
    GeneratedLearningItems,
    LearningGenerationRequest,
    ProviderCapabilities,
)

T = TypeVar("T", bound=BaseModel)


class _ConnectionProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    message: str


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        vision_enabled: bool,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.vision_enabled = vision_enabled
        self.client = client
        self.timeout_seconds = timeout_seconds

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text=True, vision=self.vision_enabled, structured_output=True)

    def _ensure_configured(self) -> None:
        if not self.base_url or not self.model or not self.api_key:
            raise AINotConfiguredError()

    async def test_connection(self) -> ConnectionTestResult:
        try:
            images = [_TEST_IMAGE] if self.vision_enabled else []
            probe = await self._validated_request(
                "只返回连接测试结果：ok 必须为 true，message 用一句短中文。",
                _ConnectionProbe,
                images,
            )
            return ConnectionTestResult(
                ok=probe.ok,
                message=probe.message,
                capabilities=self.capabilities().names(),
            )
        except AIProviderError as error:
            return ConnectionTestResult(
                ok=False,
                message=error.message,
                capabilities=self.capabilities().names(),
                error_code=error.code,
            )

    async def generate_learning_items(
        self, request: LearningGenerationRequest
    ) -> GeneratedLearningItems:
        images: list[str] = []
        for page in request.pages:
            if page.image_path is not None:
                if not self.vision_enabled:
                    raise VisionRequiredError()
                mime = mimetypes.guess_type(page.image_path.name)[0] or "image/png"
                encoded = base64.b64encode(page.image_path.read_bytes()).decode("ascii")
                images.append(f"data:{mime};base64,{encoded}")
        page_text = "\n\n".join(
            f"来源 {page.source_ref}（第 {page.page_number} 页）\n{page.extracted_text}"
            for page in request.pages
        )
        prompt = (
            f"根据以下选定课件内容生成 {request.item_count} 道主动回忆题。每题必须准确填写 "
            "source_refs，题目以概念解释、流程、对比或图片理解为主，回答与解释要简短。\n\n"
            f"{page_text}\n\n老师强调：{request.teacher_emphasis}\n"
            f"实践内容：{request.practice_content}\n个人疑问：{request.personal_questions}\n"
            f"外部学习指南：{request.notebook_text}"
        )
        return await self._validated_request(prompt, GeneratedLearningItems, images)

    async def assess_answer(self, request: AnswerAssessmentRequest) -> AnswerAssessment:
        prompt = (
            "评估学生答案。verdict 只能是 correct、partial、incorrect、unknown；"
            "missing_points 和 feedback 要简短，无法从参考答案判断时用 unknown。\n"
            f"题目：{request.question}\n参考答案：{request.reference_answer}\n"
            f"学生答案：{request.user_answer}\n来源：{', '.join(request.source_refs)}"
        )
        return await self._validated_request(prompt, AnswerAssessment, [])

    async def _validated_request(
        self, prompt: str, output_type: type[T], images: list[str]
    ) -> T:
        raw = await self._chat(prompt, output_type, images)
        try:
            return output_type.model_validate_json(raw)
        except (ValidationError, ValueError, json.JSONDecodeError):
            repair_prompt = (
                "修复下面的模型输出，使其严格符合给定 JSON Schema。只返回 JSON，不要解释。\n"
                f"原输出：\n{raw}"
            )
            repaired = await self._chat(repair_prompt, output_type, [])
            try:
                return output_type.model_validate_json(repaired)
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                raise InvalidModelOutputError() from error

    async def _chat(self, prompt: str, output_type: type[BaseModel], images: list[str]) -> str:
        self._ensure_configured()
        content: list[dict] = [{"type": "text", "text": prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": image, "detail": "high"}}
            for image in images
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是半导体课程复习助手。严格依据输入来源并输出指定 JSON。",
                },
                {"role": "user", "content": content if images else prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_type.__name__.lower(),
                    "strict": True,
                    "schema": output_type.model_json_schema(),
                },
            },
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            if self.client is not None:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers
                    )
        except httpx.TimeoutException as error:
            raise UpstreamTimeoutError() from error
        except httpx.HTTPError as error:
            raise UpstreamProviderError() from error
        if response.status_code in (401, 403):
            raise UpstreamAuthFailedError()
        if response.status_code in (408, 504):
            raise UpstreamTimeoutError()
        if response.is_error:
            raise UpstreamProviderError()
        try:
            message = response.json()["choices"][0]["message"]["content"]
            if isinstance(message, list):
                message = "".join(part.get("text", "") for part in message)
            if not isinstance(message, str):
                raise TypeError
            return message
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise InvalidModelOutputError() from error


_TEST_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
