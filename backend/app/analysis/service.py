from collections.abc import Iterable
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from sqlmodel import Session, select

from app.analysis.repository import create_analysis_run
from app.analysis.schemas import AnalysisBatchResult
from app.jobs.service import enqueue_job
from app.projects.models import ReviewProject
from app.providers.models import AIProviderProfile, ModelProfile
from app.shared.errors import AppError, NotFoundError
from app.sources.models import SourceBlock, SourceDocument


STABLE_SYSTEM_RULES = (
    "你是总复习资料分析器。只依据提供的内容提取可复习的知识点和原题；"
    "保留来源块引用和短证据，不得编造，不得自动确认任何候选结果。"
)
ANALYSIS_SCHEMA_VERSION = "candidate-v1"
ANALYSIS_PIPELINE_VERSION = "analysis-v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_prompt_prefix(project_prompt: str, run_override: str) -> str:
    schema = _canonical_json(AnalysisBatchResult.model_json_schema())
    return (
        "\n\n项目重要性规则\n"
        f"{project_prompt.strip() or '未设置；按基础定义、核心关系和常见易错点判断。'}"
        "\n\n本次分析补充规则\n"
        f"{run_override.strip() or '无额外规则。'}"
        "\n\n输出结构\n"
        f"只返回符合以下 JSON Schema 的 JSON：{schema}"
    )


def _block_cost(
    block: SourceBlock,
    image_block_ids: set[str] | None = None,
) -> tuple[int, str | None]:
    has_image = (
        block.id in image_block_ids if image_block_ids is not None else bool(block.asset_path)
    )
    image_key = None
    if has_image:
        if block.asset_path:
            image_key = f"{block.document_id}:asset:{block.asset_path}"
        elif block.page_number is not None:
            image_key = f"{block.document_id}:page:{block.page_number}"
        else:
            image_key = f"{block.document_id}:block:{block.id}"
    return len(block.text), image_key


def _sections(blocks: list[SourceBlock]) -> list[list[SourceBlock]]:
    sections: list[list[SourceBlock]] = []
    current: list[SourceBlock] = []
    current_document: int | None = None
    for block in blocks:
        if block.document_id != current_document or block.kind == "heading":
            if current:
                sections.append(current)
            current = [block]
            current_document = block.document_id
        elif current:
            current.append(block)
        else:
            current = [block]
            current_document = block.document_id
    if current:
        sections.append(current)
    return sections


def _split_oversized_section(
    section: list[SourceBlock],
    max_characters: int,
    max_images: int,
    image_block_ids: set[str] | None,
) -> list[list[SourceBlock]]:
    chunks: list[list[SourceBlock]] = []
    current: list[SourceBlock] = []
    characters = 0
    image_keys: set[str] = set()
    for block in section:
        block_characters, block_image_key = _block_cost(block, image_block_ids)
        next_image_keys = image_keys | ({block_image_key} if block_image_key else set())
        exceeds = current and (
            characters + block_characters > max_characters or len(next_image_keys) > max_images
        )
        if exceeds:
            chunks.append(current)
            current = []
            characters = 0
            image_keys = set()
            next_image_keys = {block_image_key} if block_image_key else set()
        current.append(block)
        characters += block_characters
        image_keys = next_image_keys
    if current:
        chunks.append(current)
    return chunks


def batch_source_blocks(
    blocks: Iterable[SourceBlock],
    *,
    max_characters: int,
    max_images: int,
    image_block_ids: set[str] | None = None,
) -> list[list[SourceBlock]]:
    if max_characters < 1 or max_images < 0:
        raise ValueError("Batch budgets must be positive")
    ordered = sorted(blocks, key=lambda block: (block.document_id, block.ordinal, block.id))
    units: list[list[SourceBlock]] = []
    for section in _sections(ordered):
        characters = sum(_block_cost(block, image_block_ids)[0] for block in section)
        image_keys = {
            image_key
            for block in section
            if (image_key := _block_cost(block, image_block_ids)[1]) is not None
        }
        if characters > max_characters or len(image_keys) > max_images:
            units.extend(
                _split_oversized_section(
                    section,
                    max_characters,
                    max_images,
                    image_block_ids,
                )
            )
        else:
            units.append(section)

    batches: list[list[SourceBlock]] = []
    current: list[SourceBlock] = []
    characters = 0
    image_keys: set[str] = set()
    for unit in units:
        unit_characters = sum(_block_cost(block, image_block_ids)[0] for block in unit)
        unit_image_keys = {
            image_key
            for block in unit
            if (image_key := _block_cost(block, image_block_ids)[1]) is not None
        }
        next_image_keys = image_keys | unit_image_keys
        if current and (
            characters + unit_characters > max_characters or len(next_image_keys) > max_images
        ):
            batches.append(current)
            current = []
            characters = 0
            image_keys = set()
            next_image_keys = unit_image_keys
        current.extend(unit)
        characters += unit_characters
        image_keys = next_image_keys
    if current:
        batches.append(current)
    return batches


def serialize_blocks(blocks: Iterable[SourceBlock]) -> str:
    parts = ["\n\n待分析内容"]
    for block in sorted(blocks, key=lambda item: (item.document_id, item.ordinal, item.id)):
        parts.extend(
            [
                f"BLOCK_ID: {block.id}",
                f"DOCUMENT_ID: {block.document_id}",
                f"ORDINAL: {block.ordinal}",
                f"KIND: {block.kind}",
                f"TEXT: {block.text}",
            ]
        )
    return "\n".join(parts)


def content_hash_for_blocks(blocks: Iterable[SourceBlock]) -> str:
    payload = [
        {
            "id": block.id,
            "document_id": block.document_id,
            "ordinal": block.ordinal,
            "kind": block.kind,
            "text": block.text,
            "page_number": block.page_number,
            "asset_path": block.asset_path,
        }
        for block in sorted(blocks, key=lambda item: (item.document_id, item.ordinal, item.id))
    ]
    return hash_text(_canonical_json(payload))


def clear_analysis_caches(runtime_dir: Path) -> None:
    for name in ("parse-cache", "ai-cache"):
        target = (runtime_dir / name).resolve()
        target.relative_to(runtime_dir.resolve())
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)


def resolve_analysis_scope(
    session: Session,
    project_id: str,
    *,
    mode: str,
    block_ids: list[str],
) -> list[SourceBlock]:
    project = session.get(ReviewProject, project_id)
    if project is None:
        raise NotFoundError("Review project", project_id)
    documents = session.exec(
        select(SourceDocument).where(SourceDocument.project_id == project_id)
    ).all()
    if mode == "all_sources":
        not_ready = [
            document.original_name
            for document in documents
            if document.parse_status not in {"ready", "degraded"}
        ]
        if not_ready:
            raise AppError(
                code="SOURCE_NOT_READY",
                message="部分资料仍未完成解析，请等待解析结束后再分析。",
                status_code=409,
                action="wait_for_parsing",
                context={"filenames": not_ready},
            )
        document_ids = [document.id for document in documents]
        blocks = (
            session.exec(
                select(SourceBlock)
                .where(SourceBlock.document_id.in_(document_ids))
                .order_by(SourceBlock.document_id, SourceBlock.ordinal)
            ).all()
            if document_ids
            else []
        )
    else:
        blocks = _selected_project_blocks(session, project_id, block_ids)
        selected_document_ids = {block.document_id for block in blocks}
        not_ready = [
            document.original_name
            for document in documents
            if document.id in selected_document_ids
            and document.parse_status not in {"ready", "degraded"}
        ]
        if not_ready:
            raise AppError(
                code="SOURCE_NOT_READY",
                message="所选资料仍未完成解析，请稍后重试。",
                status_code=409,
                action="wait_for_parsing",
                context={"filenames": not_ready},
            )
    if not blocks:
        raise AppError(
            code="ANALYSIS_RANGE_EMPTY",
            message="当前范围没有可分析的内容块。",
            status_code=422,
            action="select_source_blocks",
        )
    return list(blocks)


def estimate_analysis_range(
    session: Session,
    project_id: str,
    *,
    mode: str,
    block_ids: list[str],
    warning_blocks: int,
) -> dict[str, object]:
    blocks = resolve_analysis_scope(
        session,
        project_id,
        mode=mode,
        block_ids=block_ids,
    )
    document_ids = {block.document_id for block in blocks}
    documents = session.exec(
        select(SourceDocument).where(SourceDocument.id.in_(document_ids))
    ).all()
    image_count = sum(
        bool(block.asset_path)
        or (
            block.page_number is not None
            and next(document for document in documents if document.id == block.document_id).extension
            in {".pdf", ".ppt", ".pptx"}
        )
        for block in blocks
    )
    return {
        "source_count": len(document_ids),
        "block_count": len(blocks),
        "page_count": sum(document.page_count or 0 for document in documents),
        "character_count": sum(len(block.text) for block in blocks),
        "image_count": image_count,
        "exceeds_warning": len(blocks) > warning_blocks,
    }


def _selected_project_blocks(
    session: Session,
    project_id: str,
    selected_block_ids: list[str],
) -> list[SourceBlock]:
    if not selected_block_ids:
        raise AppError(
            code="ANALYSIS_RANGE_EMPTY",
            message="请至少选择一个内容块。",
            status_code=422,
            action="select_source_blocks",
        )
    blocks = session.exec(select(SourceBlock).where(SourceBlock.id.in_(selected_block_ids))).all()
    documents = {
        document.id: document
        for document in session.exec(
            select(SourceDocument).where(
                SourceDocument.id.in_({block.document_id for block in blocks})
            )
        ).all()
    }
    if len(blocks) != len(set(selected_block_ids)) or any(
        documents.get(block.document_id) is None
        or documents[block.document_id].project_id != project_id
        for block in blocks
    ):
        raise AppError(
            code="ANALYSIS_RANGE_INVALID",
            message="所选内容块不存在或不属于当前项目。",
            status_code=422,
            action="refresh_source_blocks",
        )
    return list(blocks)


def schedule_analysis(
    session: Session,
    *,
    project_id: str,
    selected_block_ids: list[str],
    provider_id: str,
    model_profile_id: str,
    run_override: str,
    parameters: dict[str, object],
    max_characters: int = 12000,
    max_images: int = 8,
):
    project = session.get(ReviewProject, project_id)
    if project is None:
        raise NotFoundError("Review project", project_id)
    provider = session.get(AIProviderProfile, provider_id)
    if provider is None:
        raise NotFoundError("Provider", provider_id)
    if not provider.enabled:
        raise AppError(
            code="PROVIDER_NOT_ENABLED",
            message="所选第三方服务尚未启用。",
            status_code=409,
            action="open_provider_settings",
        )
    model = session.get(ModelProfile, model_profile_id)
    if model is None or model.provider_id != provider_id:
        raise NotFoundError("Model", model_profile_id)
    if model.structured_status != "passed":
        raise AppError(
            code="MODEL_CAPABILITY_NOT_VALIDATED",
            message="所选模型尚未通过结构化输出校验。",
            status_code=409,
            action="open_provider_settings",
        )
    blocks = _selected_project_blocks(session, project_id, selected_block_ids)
    documents = {
        document.id: document
        for document in session.exec(
            select(SourceDocument).where(
                SourceDocument.id.in_({block.document_id for block in blocks})
            )
        ).all()
    }
    image_block_ids = {
        block.id
        for block in blocks
        if block.asset_path
        or (
            block.page_number is not None
            and documents[block.document_id].extension in {".pdf", ".ppt", ".pptx"}
        )
    }
    if image_block_ids and model.vision_status != "passed":
        raise AppError(
            code="MODEL_VISION_NOT_VALIDATED",
            message="所选内容包含图片或页面预览，但模型尚未通过视觉能力校验。",
            status_code=409,
            action="choose_vision_model",
        )
    batches = batch_source_blocks(
        blocks,
        max_characters=max_characters,
        max_images=max_images,
        image_block_ids=image_block_ids,
    )
    prompt_prefix = build_prompt_prefix(project.importance_prompt, run_override)
    run = create_analysis_run(
        session,
        project_id=project_id,
        selected_block_ids=selected_block_ids,
        prompt_snapshot=prompt_prefix,
        provider_id=provider.id,
        provider_config_generation=provider.credential_generation,
        provider_protocol=provider.protocol,
        provider_base_url=provider.base_url,
        model_id=model.model_id,
        schema_version=ANALYSIS_SCHEMA_VERSION,
        pipeline_version=ANALYSIS_PIPELINE_VERSION,
        batches=[[block.id for block in batch] for batch in batches],
        parameters=parameters,
        commit=False,
    )
    job = enqueue_job(session, "analysis_run", {"run_id": run.id}, max_attempts=5)
    session.refresh(run)
    return run, job


def retry_failed_batches(session: Session, run_id: int):
    from app.analysis.models import AnalysisBatch, AnalysisRun

    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFoundError("Analysis run", str(run_id))
    failed = session.exec(
        select(AnalysisBatch).where(
            AnalysisBatch.run_id == run_id,
            AnalysisBatch.status == "failed",
        )
    ).all()
    if not failed:
        raise AppError(
            code="NO_FAILED_BATCHES",
            message="当前任务没有可重试的失败批次。",
            status_code=409,
            action="create_new_analysis",
        )
    for batch in failed:
        batch.status = "queued"
        batch.public_error_code = None
        batch.error_detail = None
        session.add(batch)
    run.status = "queued"
    run.failed_batches = 0
    run.cancellation_requested = False
    run.public_error_code = None
    run.error_detail = None
    session.add(run)
    session.flush()
    job = enqueue_job(session, "analysis_run", {"run_id": run.id}, max_attempts=5)
    session.refresh(run)
    return run, job, [batch.id for batch in failed]
