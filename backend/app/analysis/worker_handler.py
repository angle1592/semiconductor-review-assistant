import asyncio
import base64
import json
import mimetypes
from pathlib import Path
from pathlib import PurePosixPath

from sqlmodel import Session, select

from app.analysis.cache import AIResultCache, analysis_cache_key
from app.analysis.models import AnalysisBatch, AnalysisRun
from app.analysis.repository import process_analysis_batches
from app.analysis.schemas import AnalysisBatchResult
from app.analysis.service import (
    STABLE_SYSTEM_RULES,
    content_hash_for_blocks,
    hash_text,
    serialize_blocks,
)
from app.providers.contracts import StructuredRequest
from app.providers.credentials import SecretStore, credential_key
from app.providers.models import AIProviderProfile
from app.shared.errors import AppError, NotFoundError
from app.sources.models import SourceBlock, SourceDocument


def validate_batch_result_references(
    result: AnalysisBatchResult,
    allowed_block_ids: set[str],
) -> None:
    references = {
        block_id
        for item in [*result.candidates, *result.source_questions]
        for block_id in item.source_block_ids
    }
    if not references <= allowed_block_ids:
        raise AppError(
            code="MODEL_CITATION_OUTSIDE_BATCH",
            message="模型引用了本批次之外的资料块，结果已拒绝保存。",
            status_code=422,
            action="retry_analysis_batch",
            context={"outside_block_ids": sorted(references - allowed_block_ids)},
        )


class AnalysisWorkerHandler:
    def __init__(
        self,
        engine,
        runtime_dir: Path,
        secrets: SecretStore,
        adapter_factory,
        *,
        data_dir: Path | None = None,
    ):
        self.engine = engine
        self.cache = AIResultCache(runtime_dir / "ai-cache")
        self.secrets = secrets
        self.adapter_factory = adapter_factory
        self.data_dir = data_dir.resolve() if data_dir is not None else None

    def __call__(self, payload: dict[str, object]) -> str | None:
        run_id = int(payload["run_id"])
        process_analysis_batches(self.engine, run_id, self._process_batch)
        with Session(self.engine) as session:
            run = session.get(AnalysisRun, run_id)
            return "cancelled" if run is not None and run.status == "cancelled" else None

    def on_terminal_failure(
        self,
        payload: dict[str, object],
        public_error_code: str,
        error_detail: str,
    ) -> None:
        run_id = int(payload["run_id"])
        with Session(self.engine) as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                return
            batches = session.exec(
                select(AnalysisBatch).where(AnalysisBatch.run_id == run_id)
            ).all()
            for batch in batches:
                if batch.status == "running":
                    batch.status = "failed"
                    batch.public_error_code = public_error_code
                    batch.error_detail = error_detail
                    session.add(batch)
            run.completed_batches = sum(batch.status == "succeeded" for batch in batches)
            run.failed_batches = sum(batch.status == "failed" for batch in batches)
            run.status = "partial" if run.completed_batches else "failed"
            run.public_error_code = public_error_code
            run.error_detail = error_detail
            session.add(run)
            session.commit()

    def _batch_context(
        self,
        batch_id: int,
        block_ids: tuple[str, ...],
    ) -> tuple[AnalysisBatch, AnalysisRun, list[SourceBlock]]:
        with Session(self.engine) as session:
            batch = session.get(AnalysisBatch, batch_id)
            if batch is None:
                raise NotFoundError("Analysis batch", str(batch_id))
            run = session.get(AnalysisRun, batch.run_id)
            if run is None:
                raise NotFoundError("Analysis run", str(batch.run_id))
            blocks = session.exec(select(SourceBlock).where(SourceBlock.id.in_(block_ids))).all()
            if len(blocks) != len(block_ids):
                raise AppError(
                    code="SOURCE_BLOCK_MISSING",
                    message="分析所需的资料块已不存在。",
                    status_code=409,
                    action="create_new_analysis",
                )
            session.expunge(batch)
            session.expunge(run)
            for block in blocks:
                session.expunge(block)
            return batch, run, list(blocks)

    def _record_cache_usage(
        self,
        batch_id: int,
        *,
        cache_status: str,
        cached_input_tokens: int = 0,
        cache_usage_reported: bool = False,
    ) -> None:
        with Session(self.engine) as session:
            batch = session.get(AnalysisBatch, batch_id)
            if batch is None:
                return
            batch.cache_status = cache_status
            batch.provider_cached_input_tokens = cached_input_tokens
            batch.provider_cache_usage_reported = cache_usage_reported
            session.add(batch)
            session.commit()

    def _image_data_urls(self, blocks: list[SourceBlock]) -> list[str]:
        if self.data_dir is None:
            return []
        document_ids = {block.document_id for block in blocks}
        with Session(self.engine) as session:
            documents = {
                document.id: document
                for document in session.exec(
                    select(SourceDocument).where(SourceDocument.id.in_(document_ids))
                ).all()
            }
        paths: list[Path] = []
        for block in blocks:
            document = documents.get(block.document_id)
            if document is None:
                continue
            relative = block.asset_path
            if relative is None and block.page_number is not None:
                if document.extension == ".pdf":
                    relative = f"pages/page-{block.page_number:04d}.png"
                elif document.extension in {".ppt", ".pptx"}:
                    relative = f"slides/slide-{block.page_number:04d}.png"
            if relative is None:
                continue
            relative_path = PurePosixPath(relative.replace("\\", "/"))
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise AppError(
                    code="INVALID_SOURCE_ASSET_PATH",
                    message="资料中的图片路径无效。",
                    status_code=409,
                    action="reimport_source",
                )
            source_file = (self.data_dir / document.stored_name).resolve()
            assets_root = (source_file.parent / "assets").resolve()
            candidate = (assets_root / Path(*relative_path.parts)).resolve()
            try:
                candidate.relative_to(assets_root)
            except ValueError as error:
                raise AppError(
                    code="INVALID_SOURCE_ASSET_PATH",
                    message="资料中的图片路径无效。",
                    status_code=409,
                    action="reimport_source",
                ) from error
            if not candidate.is_file():
                raise AppError(
                    code="SOURCE_ASSET_MISSING",
                    message="资料预览图片已丢失，请重新导入资料。",
                    status_code=409,
                    action="reimport_source",
                )
            if candidate not in paths:
                paths.append(candidate)
        images: list[str] = []
        for path in paths:
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            images.append(f"data:{media_type};base64,{encoded}")
        return images

    def _process_batch(
        self,
        batch_id: int,
        block_ids: tuple[str, ...],
    ) -> dict[str, object]:
        _batch, run, blocks = self._batch_context(batch_id, block_ids)
        parameters = json.loads(run.parameters_json)
        content_hash = content_hash_for_blocks(blocks)
        prompt_hash = hash_text(f"{STABLE_SYSTEM_RULES}\0{run.prompt_snapshot}")
        key = analysis_cache_key(
            protocol=run.provider_protocol,
            provider_config_generation=run.provider_config_generation,
            model=run.model_id,
            content_hash=content_hash,
            prompt_hash=prompt_hash,
            schema_version=run.schema_version,
            pipeline_version=run.pipeline_version,
            parameters=parameters,
        )
        cached = self.cache.load(key)
        if cached is not None:
            self._record_cache_usage(batch_id, cache_status="hit")
            return cached.model_dump(mode="json")

        api_key = self.secrets.get(credential_key(run.provider_id))
        if not api_key:
            raise AppError(
                code="PROVIDER_CREDENTIAL_MISSING",
                message="第三方服务密钥不存在，请重新填写并校验。",
                status_code=409,
                action="replace_api_key",
            )
        profile_snapshot = AIProviderProfile(
            id=run.provider_id,
            name="analysis-snapshot",
            protocol=run.provider_protocol,
            base_url=run.provider_base_url,
            enabled=True,
            credential_generation=run.provider_config_generation,
        )
        adapter = self.adapter_factory(profile_snapshot, api_key)
        request = StructuredRequest(
            model=run.model_id,
            prompt=serialize_blocks(blocks),
            prompt_prefix=run.prompt_snapshot,
            output_type=AnalysisBatchResult,
            system=STABLE_SYSTEM_RULES,
            images=self._image_data_urls(blocks),
            cache_system=run.provider_protocol == "anthropic",
            cache_prompt_prefix=run.provider_protocol == "anthropic",
            temperature=float(parameters.get("temperature", 0)),
        )
        provider_result = asyncio.run(adapter.generate_json(request))
        value = AnalysisBatchResult.model_validate(provider_result.value)
        validate_batch_result_references(value, set(block_ids))
        self.cache.store(
            key,
            value,
            status="succeeded",
            metadata={
                "protocol": run.provider_protocol,
                "provider_config_generation": run.provider_config_generation,
                "model": run.model_id,
                "cache_usage_reported": provider_result.cache_usage_reported,
                "cached_input_tokens": provider_result.cached_input_tokens,
                "cache_creation_input_tokens": provider_result.cache_creation_input_tokens,
            },
        )
        self._record_cache_usage(
            batch_id,
            cache_status="miss",
            cached_input_tokens=provider_result.cached_input_tokens,
            cache_usage_reported=provider_result.cache_usage_reported,
        )
        return value.model_dump(mode="json")
