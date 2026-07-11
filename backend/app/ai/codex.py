import asyncio
import base64
import importlib
import inspect
import json
from contextlib import suppress
from pathlib import Path
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.errors import (
    AIProviderError,
    InvalidModelOutputError,
    ProviderUnavailableError,
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
    ok: bool
    message: str


def _import_sdk():
    return importlib.import_module("openai_codex")


class CodexProvider:
    def __init__(
        self,
        *,
        model: str,
        data_dir: str | Path,
        vision_enabled: bool,
        timeout_seconds: float = 60,
        sdk_loader: Callable = _import_sdk,
    ):
        self.model = model
        self.workspace = (Path(data_dir) / "codex-provider").resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.vision_enabled = vision_enabled
        self.timeout_seconds = timeout_seconds
        self.sdk_loader = sdk_loader

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text=True, vision=self.vision_enabled, structured_output=True)

    def _sdk(self):
        try:
            return self.sdk_loader()
        except (ImportError, ModuleNotFoundError) as error:
            raise ProviderUnavailableError(
                "Codex SDK is unavailable. Install openai-codex==0.1.0b3."
            ) from error

    async def test_connection(self) -> ConnectionTestResult:
        try:
            sdk = self._sdk()

            async def probe():
                codex = sdk.AsyncCodex()
                try:
                    account = await codex.account()
                    models = await codex.models(include_hidden=True)
                    return account, models
                finally:
                    await _close_codex(codex, self.timeout_seconds)

            account, models = await asyncio.wait_for(probe(), timeout=self.timeout_seconds)
            if getattr(account, "account", account) is None:
                raise UpstreamAuthFailedError()
            if self.model and not _model_exists(models, self.model):
                return ConnectionTestResult(
                    ok=False,
                    message=f"Codex model is unavailable: {self.model}",
                    capabilities=self.capabilities().names(),
                    error_code="MODEL_NOT_FOUND",
                )
            probe_images: list[Path] = []
            probe_image: Path | None = None
            if self.vision_enabled:
                probe_image = self.workspace / "connection-probe.png"
                probe_image.write_bytes(base64.b64decode(_TEST_IMAGE_BASE64))
                probe_images.append(probe_image)
            try:
                probe_result = await self._validated_run(
                    "返回连接测试 JSON：ok 为 true，message 用一句短中文。"
                    "如果提供了图片，确认你可以读取该图片。不得调用任何工具。",
                    _ConnectionProbe,
                    probe_images,
                )
            finally:
                if probe_image is not None:
                    probe_image.unlink(missing_ok=True)
            if not probe_result.ok:
                raise UpstreamProviderError("Codex generation probe failed.")
            return ConnectionTestResult(
                ok=True,
                message=probe_result.message,
                capabilities=self.capabilities().names(),
            )
        except ProviderUnavailableError as error:
            return ConnectionTestResult(
                ok=False,
                available=False,
                message=error.message,
                error_code="CODEX_SDK_UNAVAILABLE",
            )
        except asyncio.TimeoutError:
            error = UpstreamTimeoutError()
        except AIProviderError as provider_error:
            error = provider_error
        except Exception:
            error = UpstreamProviderError("Codex connection test failed.")
        return ConnectionTestResult(
            ok=False,
            message=error.message,
            capabilities=self.capabilities().names(),
            error_code=error.code,
        )

    async def generate_learning_items(
        self, request: LearningGenerationRequest
    ) -> GeneratedLearningItems:
        image_paths = [page.image_path for page in request.pages if page.image_path is not None]
        if image_paths and not self.vision_enabled:
            raise VisionRequiredError()
        source_text = "\n\n".join(
            f"来源 {page.source_ref}（第 {page.page_number} 页）\n{page.extracted_text}"
            for page in request.pages
        )
        prompt = (
            f"依据以下内容生成 {request.item_count} 道半导体主动回忆题。每题必须包含来源，"
            "答案与解释简短。不得使用 shell、网络、工具或读取其他文件。\n"
            f"{source_text}\n老师强调：{request.teacher_emphasis}\n"
            f"实践：{request.practice_content}\n疑问：{request.personal_questions}\n"
            f"学习指南：{request.notebook_text}"
        )
        return await self._validated_run(prompt, GeneratedLearningItems, image_paths)

    async def assess_answer(self, request: AnswerAssessmentRequest) -> AnswerAssessment:
        prompt = (
            "只根据题目和参考答案评估学生回答，不得使用 shell、网络或其他工具。"
            "verdict 为 correct、partial、incorrect 或 unknown。\n"
            f"题目：{request.question}\n参考：{request.reference_answer}\n回答：{request.user_answer}"
        )
        return await self._validated_run(prompt, AnswerAssessment, [])

    async def _validated_run(self, prompt: str, output_type: type[T], image_paths: list[Path]) -> T:
        raw = await self._run_once(prompt, output_type, image_paths)
        try:
            return output_type.model_validate_json(raw)
        except (ValidationError, ValueError, json.JSONDecodeError):
            repair = (
                "修复下列内容，使其严格符合提供的 JSON Schema。仅输出 JSON，不使用任何工具。\n"
                f"{raw}"
            )
            repaired = await self._run_once(repair, output_type, [])
            try:
                return output_type.model_validate_json(repaired)
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                raise InvalidModelOutputError() from error

    async def _run_once(
        self, prompt: str, output_type: type[BaseModel], image_paths: list[Path]
    ) -> str:
        sdk = self._sdk()
        inputs = [sdk.TextInput(prompt)]
        inputs.extend(sdk.LocalImageInput(str(path.resolve())) for path in image_paths)
        restricted_config = {
            "web_search": "disabled",
            "features": {
                "shell_tool": False,
                "unified_exec": False,
                "web_search": False,
                "standalone_web_search": False,
                "browser_use": False,
                "computer_use": False,
            },
        }
        codex = None
        turn = None
        try:
            codex = sdk.AsyncCodex()

            async def execute_turn():
                nonlocal turn
                thread = await codex.thread_start(
                    model=self.model or None,
                    cwd=str(self.workspace),
                    ephemeral=True,
                    approval_mode=sdk.ApprovalMode.deny_all,
                    sandbox=sdk.Sandbox.read_only,
                    config=restricted_config,
                    developer_instructions=(
                        "Never use shell, web, browser, computer, MCP, skills, or external tools. "
                        "Only transform the supplied text/images into the requested JSON."
                    ),
                )
                turn = await thread.turn(
                    inputs,
                    approval_mode=sdk.ApprovalMode.deny_all,
                    sandbox=sdk.Sandbox.read_only,
                    output_schema=output_type.model_json_schema(),
                )
                return await turn.run()

            try:
                result = await asyncio.wait_for(execute_turn(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError as error:
                if turn is not None:
                    interrupt_timeout = min(2.0, max(0.05, self.timeout_seconds))
                    with suppress(Exception):
                        await asyncio.wait_for(turn.interrupt(), timeout=interrupt_timeout)
                raise UpstreamTimeoutError() from error
        except AIProviderError:
            raise
        except Exception as error:
            raise UpstreamProviderError("Codex generation failed.") from error
        finally:
            if codex is not None:
                await _close_codex(codex, self.timeout_seconds)
        if not isinstance(result.final_response, str):
            raise InvalidModelOutputError()
        return result.final_response


async def _close_codex(codex, timeout_seconds: float) -> None:
    close = getattr(codex, "close", None)
    if close is None:
        return
    with suppress(Exception):
        result = close()
        if inspect.isawaitable(result):
            close_timeout = min(2.0, max(0.05, timeout_seconds))
            await asyncio.wait_for(result, timeout=close_timeout)


def _model_exists(response, model: str) -> bool:
    entries = getattr(response, "data", getattr(response, "models", None))
    if entries is None:
        return True  # Older SDK servers do not expose a normalized model list.
    for entry in entries:
        identifier = getattr(entry, "id", getattr(entry, "model", None))
        if identifier == model:
            return True
    return False


_TEST_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
