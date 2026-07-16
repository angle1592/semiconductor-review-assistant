import asyncio
import json

from sqlmodel import Session, select

from app.analysis.cache import AIResultCache, analysis_cache_key
from app.analysis.service import hash_text
from app.keypoints.models import KeyPoint
from app.providers.contracts import StructuredRequest
from app.providers.credentials import SecretStore, credential_key
from app.providers.models import AIProviderProfile
from app.shared.errors import AppError
from app.study.models import GeneratedArtifact, SourceQuestion
from app.study.schemas import ArtifactGenerationResult


SYSTEM = "你是总复习材料生成器。只依据已确认重点和所选原题生成内容，保留 ID，不得编造来源。"


class ArtifactWorkerHandler:
    def __init__(self, engine, runtime_dir, secrets: SecretStore, adapter_factory):
        self.engine = engine
        self.cache = AIResultCache(runtime_dir / "ai-cache", ArtifactGenerationResult)
        self.secrets = secrets
        self.adapter_factory = adapter_factory

    def __call__(self, payload: dict[str, object]) -> None:
        artifact_id = int(payload["artifact_id"])
        with Session(self.engine) as session:
            artifact = session.get(GeneratedArtifact, artifact_id)
            if artifact is None or artifact.status == "succeeded":
                return
            artifact.status = "running"
            session.add(artifact)
            session.commit()
            keypoint_ids = [int(value) for value in json.loads(artifact.keypoint_ids_json)]
            question_ids = [int(value) for value in json.loads(artifact.source_question_ids_json)]
            keypoints = session.exec(select(KeyPoint).where(KeyPoint.id.in_(keypoint_ids))).all()
            questions = session.exec(select(SourceQuestion).where(SourceQuestion.id.in_(question_ids))).all() if question_ids else []
            content = json.dumps(
                {
                    "kind": artifact.kind,
                    "keypoints": [{"id": point.id, "title": point.title, "explanation": point.explanation} for point in keypoints],
                    "source_questions": [{"id": question.id, "question": question.question_text, "answer": question.answer_text} for question in questions],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            key = analysis_cache_key(
                protocol=artifact.provider_protocol,
                provider_config_generation=artifact.provider_config_generation,
                model=artifact.model_id,
                content_hash=hash_text(content),
                prompt_hash=artifact.prompt_hash,
                schema_version="artifact-v1",
                pipeline_version="study-v1",
                parameters={"temperature": 0},
            )
            cached = self.cache.load(key)
            if cached is not None:
                result = ArtifactGenerationResult.model_validate(cached.model_dump())
                artifact.cache_status = "hit"
            else:
                api_key = self.secrets.get(credential_key(artifact.provider_id))
                if not api_key:
                    raise AppError(code="PROVIDER_CREDENTIAL_MISSING", message="第三方服务密钥不存在。", status_code=409, action="replace_api_key")
                profile = AIProviderProfile(id=artifact.provider_id, name="artifact-snapshot", protocol=artifact.provider_protocol, base_url=artifact.provider_base_url, enabled=True, credential_generation=artifact.provider_config_generation)
                adapter = self.adapter_factory(profile, api_key)
                response = asyncio.run(adapter.generate_json(StructuredRequest(model=artifact.model_id, system=SYSTEM, prompt_prefix=artifact.prompt_snapshot, prompt=content, output_type=ArtifactGenerationResult, temperature=0)))
                result = ArtifactGenerationResult.model_validate(response.value)
                referenced_keypoints = {value for card in result.flashcards for value in card.keypoint_ids} | {value for question in result.questions for value in question.keypoint_ids} | ({value for section in result.outline.sections for value in section.keypoint_ids} if result.outline else set())
                referenced_questions = {value for question in result.questions for value in question.source_question_ids}
                if not referenced_keypoints <= set(keypoint_ids) or not referenced_questions <= set(question_ids):
                    raise AppError(code="MODEL_CITATION_OUTSIDE_SELECTION", message="模型引用了未选择的重点或原题。", status_code=422, action="retry_artifact_generation")
                self.cache.store(key, result, status="succeeded", metadata={"model": artifact.model_id, "kind": artifact.kind})
                artifact.cache_status = "miss"
            artifact.payload_json = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            artifact.status = "succeeded"
            artifact.public_error_code = None
            artifact.error_detail = None
            session.add(artifact)
            session.commit()

    def on_terminal_failure(self, payload, public_error_code: str, error_detail: str):
        with Session(self.engine) as session:
            artifact = session.get(GeneratedArtifact, int(payload["artifact_id"]))
            if artifact is not None:
                artifact.status = "failed"
                artifact.public_error_code = public_error_code
                artifact.error_detail = error_detail
                session.add(artifact)
                session.commit()
