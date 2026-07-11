from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.codex import CodexProvider
from app.ai.errors import ProviderUnavailableError, UpstreamTimeoutError
from app.ai.schemas import LearningGenerationRequest, LearningSourcePage


def missing_sdk():
    raise ModuleNotFoundError("No module named 'openai_codex'")


@pytest.mark.asyncio
async def test_codex_missing_sdk_is_lazy_and_reported_without_boot_failure(tmp_path: Path) -> None:
    provider = CodexProvider(
        model="gpt-codex",
        data_dir=tmp_path,
        vision_enabled=False,
        sdk_loader=missing_sdk,
    )

    result = await provider.test_connection()

    assert result.ok is False
    assert result.available is False
    assert result.error_code == "CODEX_SDK_UNAVAILABLE"
    assert "openai-codex" in result.message
    with pytest.raises(ProviderUnavailableError):
        await provider.generate_learning_items(
            LearningGenerationRequest(
                pages=[LearningSourcePage(source_ref="notes#1", page_number=1)],
                item_count=1,
            )
        )


@pytest.mark.asyncio
async def test_codex_connection_runs_a_restricted_visual_probe(tmp_path: Path) -> None:
    seen_inputs: list[object] = []

    class ApprovalMode:
        deny_all = "deny_all"

    class Sandbox:
        read_only = "read_only"

    class TextInput:
        def __init__(self, text: str):
            self.text = text

    class LocalImageInput:
        def __init__(self, path: str):
            self.path = path

    class Turn:
        async def run(self):
            return SimpleNamespace(final_response='{"ok":true,"message":"视觉可用"}')

        async def interrupt(self):  # pragma: no cover - timeout path
            return None

    class Thread:
        async def turn(self, inputs, **_kwargs):
            seen_inputs.extend(inputs)
            return Turn()

    class AsyncCodex:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def account(self):
            return SimpleNamespace(account=object())

        async def models(self, **_kwargs):
            return SimpleNamespace(data=[SimpleNamespace(id="gpt-codex")])

        async def thread_start(self, **_kwargs):
            return Thread()

    class SDK:
        pass

    SDK.AsyncCodex = AsyncCodex
    SDK.ApprovalMode = ApprovalMode
    SDK.Sandbox = Sandbox
    SDK.TextInput = TextInput
    SDK.LocalImageInput = LocalImageInput

    provider = CodexProvider(
        model="gpt-codex",
        data_dir=tmp_path,
        vision_enabled=True,
        sdk_loader=lambda: SDK,
    )

    result = await provider.test_connection()

    assert result.ok is True
    assert "vision" in result.capabilities
    assert any(isinstance(value, LocalImageInput) for value in seen_inputs)


@pytest.mark.asyncio
async def test_codex_uses_ephemeral_restricted_thread_and_local_images(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"image")
    seen: dict[str, object] = {}

    class ApprovalMode:
        deny_all = "deny_all"

    class Sandbox:
        read_only = "read_only"

    class TextInput:
        def __init__(self, text: str):
            self.text = text

    class LocalImageInput:
        def __init__(self, path: str):
            self.path = path

    class Result:
        final_response = (
            '{"items":[{"topic":"氧化","question":"目的？",'
            '"reference_answer":"形成氧化层","explanation":"绝缘与掩膜",'
            '"source_refs":["slide#2"]}]}'
        )

    class Turn:
        async def run(self):
            return Result()

        async def interrupt(self):  # pragma: no cover - timeout path
            seen["interrupted"] = True

    class Thread:
        async def turn(self, inputs, **kwargs):
            seen["inputs"] = inputs
            seen["turn_kwargs"] = kwargs
            return Turn()

    class AsyncCodex:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def thread_start(self, **kwargs):
            seen["thread_kwargs"] = kwargs
            return Thread()

    class SDK:
        pass

    SDK.AsyncCodex = AsyncCodex
    SDK.ApprovalMode = ApprovalMode
    SDK.Sandbox = Sandbox
    SDK.TextInput = TextInput
    SDK.LocalImageInput = LocalImageInput

    provider = CodexProvider(
        model="gpt-codex",
        data_dir=tmp_path,
        vision_enabled=True,
        sdk_loader=lambda: SDK,
    )
    generated = await provider.generate_learning_items(
        LearningGenerationRequest(
            pages=[
                LearningSourcePage(
                    source_ref="slide#2",
                    page_number=2,
                    extracted_text="热氧化",
                    image_path=image_path,
                )
            ],
            item_count=1,
        )
    )

    assert generated.items[0].topic == "氧化"
    thread_kwargs = seen["thread_kwargs"]
    assert thread_kwargs["ephemeral"] is True
    assert thread_kwargs["approval_mode"] == "deny_all"
    assert thread_kwargs["sandbox"] == "read_only"
    assert Path(thread_kwargs["cwd"]).name == "codex-provider"
    assert thread_kwargs["config"]["web_search"] == "disabled"
    assert thread_kwargs["config"]["features"]["shell_tool"] is False
    assert any(
        isinstance(value, LocalImageInput) and value.path == str(image_path.resolve())
        for value in seen["inputs"]
    )
    assert seen["turn_kwargs"]["output_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_codex_timeout_does_not_hang_when_interrupt_stalls(tmp_path: Path) -> None:
    import asyncio

    class ApprovalMode:
        deny_all = "deny_all"

    class Sandbox:
        read_only = "read_only"

    class TextInput:
        def __init__(self, text):
            self.text = text

    class LocalImageInput:
        def __init__(self, path):
            self.path = path

    class Turn:
        async def run(self):
            await asyncio.sleep(10)

        async def interrupt(self):
            await asyncio.sleep(10)

    class Thread:
        async def turn(self, *_args, **_kwargs):
            return Turn()

    class AsyncCodex:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            await asyncio.sleep(10)

        async def close(self):
            await asyncio.sleep(10)

        async def thread_start(self, **_kwargs):
            return Thread()

    class SDK:
        pass

    SDK.AsyncCodex = AsyncCodex
    SDK.ApprovalMode = ApprovalMode
    SDK.Sandbox = Sandbox
    SDK.TextInput = TextInput
    SDK.LocalImageInput = LocalImageInput

    provider = CodexProvider(
        model="",
        data_dir=tmp_path,
        vision_enabled=False,
        timeout_seconds=0.01,
        sdk_loader=lambda: SDK,
    )

    with pytest.raises(UpstreamTimeoutError):
        await asyncio.wait_for(
            provider.generate_learning_items(
                LearningGenerationRequest(
                    pages=[LearningSourcePage(source_ref="probe", page_number=1)],
                    item_count=1,
                )
            ),
            timeout=0.3,
        )


@pytest.mark.asyncio
async def test_codex_timeout_covers_thread_start(tmp_path: Path) -> None:
    import asyncio

    class ApprovalMode:
        deny_all = "deny_all"

    class Sandbox:
        read_only = "read_only"

    class TextInput:
        def __init__(self, text):
            self.text = text

    class LocalImageInput:
        def __init__(self, path):
            self.path = path

    class AsyncCodex:
        async def thread_start(self, **_kwargs):
            await asyncio.sleep(10)

        async def close(self):
            return None

    class SDK:
        pass

    SDK.AsyncCodex = AsyncCodex
    SDK.ApprovalMode = ApprovalMode
    SDK.Sandbox = Sandbox
    SDK.TextInput = TextInput
    SDK.LocalImageInput = LocalImageInput

    provider = CodexProvider(
        model="gpt-codex",
        data_dir=tmp_path,
        vision_enabled=False,
        timeout_seconds=0.01,
        sdk_loader=lambda: SDK,
    )

    with pytest.raises(UpstreamTimeoutError):
        await asyncio.wait_for(
            provider.generate_learning_items(
                LearningGenerationRequest(
                    pages=[LearningSourcePage(source_ref="probe", page_number=1)],
                    item_count=1,
                )
            ),
            timeout=0.3,
        )
