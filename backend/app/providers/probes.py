from datetime import UTC, datetime

from pydantic import BaseModel

from app.providers.contracts import ProviderAdapter, StructuredRequest, TextRequest
from app.providers.errors import ProviderError
from app.providers.models import ModelProfile


VISION_PROBE_IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


class ProbeOutput(BaseModel):
    ok: bool
    message: str


def reset_probe_states(model: ModelProfile) -> None:
    model.text_status = "untested"
    model.structured_status = "untested"
    model.vision_status = "untested"
    model.prompt_cache_status = "untested"
    model.safe_error_code = None
    model.validated_at = None


def required_probes_passed(model: ModelProfile) -> bool:
    return all(status == "passed" for status in (model.text_status, model.structured_status, model.vision_status))


async def _run(probe) -> tuple[str, str | None]:
    try:
        await probe
        return "passed", None
    except ProviderError as error:
        return "failed", error.code
    except (ValueError, TypeError):
        return "failed", "upstream_invalid_response"


async def probe_model(adapter: ProviderAdapter, protocol: str, model: ModelProfile) -> None:
    model.text_status, model.safe_error_code = await _run(adapter.generate_text(TextRequest(model=model.model_id, prompt="只回答 OK。")))
    model.structured_status, structured_error = await _run(adapter.generate_json(StructuredRequest(model=model.model_id, prompt="返回校验结果。", output_type=ProbeOutput)))
    model.safe_error_code = model.safe_error_code or structured_error
    model.vision_status, vision_error = await _run(adapter.generate_text(TextRequest(model=model.model_id, prompt="确认你收到了一张测试图片，只回答 OK。", images=[VISION_PROBE_IMAGE])))
    model.safe_error_code = model.safe_error_code or vision_error
    if protocol == "anthropic" and hasattr(adapter, "probe_prompt_cache"):
        try:
            await adapter.probe_prompt_cache(model.model_id)
            model.prompt_cache_status = "passed"
        except ProviderError as error:
            model.prompt_cache_status = "unsupported" if error.code in {"prompt_cache_unsupported", "upstream_invalid_response"} else "failed"
            model.safe_error_code = model.safe_error_code or error.code
    else:
        model.prompt_cache_status = "unsupported"
    model.validated_at = datetime.now(UTC)
