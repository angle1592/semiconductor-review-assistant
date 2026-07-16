import json
from datetime import UTC, timedelta
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.analysis.repository import request_run_cancellation
from app.analysis.schemas import AnalysisBatchResult, KeyPointCandidate
from app.analysis.service import (
    STABLE_SYSTEM_RULES,
    batch_source_blocks,
    build_prompt_prefix,
    schedule_analysis,
)
from app.analysis.worker_handler import AnalysisWorkerHandler, validate_batch_result_references
from app.providers.anthropic import AnthropicAdapter
from app.providers.contracts import ProviderResult, StructuredRequest
from app.providers.credentials import MemorySecretStore, credential_key
from app.providers.endpoints import resolve_endpoints
from app.providers.models import AIProviderProfile, ModelProfile
from app.jobs.models import DurableJob
from app.jobs.worker import DurableWorker
from app.projects.models import ReviewProject
from app.shared.database import create_database
from app.shared.errors import AppError
from app.sources.models import SourceBlock, SourceDocument


def make_block(
    block_id: str,
    *,
    document_id: int,
    ordinal: int,
    kind: str,
    text: str,
    asset_path: str | None = None,
) -> SourceBlock:
    return SourceBlock(
        id=block_id,
        document_id=document_id,
        ordinal=ordinal,
        locator=f"block:{ordinal}",
        kind=kind,
        text=text,
        asset_path=asset_path,
    )


def test_deterministic_batching_keeps_heading_with_following_content():
    blocks = [
        make_block("p2", document_id=2, ordinal=1, kind="paragraph", text="后一个文档"),
        make_block("p1", document_id=1, ordinal=1, kind="paragraph", text="公式说明"),
        make_block("h1", document_id=1, ordinal=0, kind="heading", text="第一章"),
        make_block("p3", document_id=1, ordinal=2, kind="paragraph", text="易错点"),
    ]

    batches = batch_source_blocks(blocks, max_characters=10, max_images=1)

    assert [[block.id for block in batch] for batch in batches] == [
        ["h1", "p1", "p3"],
        ["p2"],
    ]


def test_prompt_prefix_has_fixed_order_before_content():
    prefix = build_prompt_prefix("优先项目公式", "本次只看易错点")

    assert prefix.index("项目重要性规则") < prefix.index("本次分析补充规则")
    assert prefix.index("本次分析补充规则") < prefix.index("输出结构")
    assert "优先项目公式" in prefix
    assert "本次只看易错点" in prefix
    assert "待分析内容" not in prefix
    assert "不得自动确认" in STABLE_SYSTEM_RULES


def test_candidate_references_must_stay_inside_the_batch():
    result = AnalysisBatchResult(
        candidates=[
            KeyPointCandidate(
                title="越界引用",
                explanation="错误引用",
                importance="important",
                source_block_ids=["outside"],
                evidence_quotes=["短证据"],
                rationale="测试",
            )
        ],
        source_questions=[],
    )

    with pytest.raises(AppError) as caught:
        validate_batch_result_references(result, {"inside"})

    assert caught.value.code == "MODEL_CITATION_OUTSIDE_BATCH"


@pytest.mark.asyncio
async def test_anthropic_marks_stable_system_and_prompt_prefix_for_cache():
    captured: dict = {}

    async def handler(request: httpx.Request):
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"candidates":[],"source_questions":[]}'}],
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicAdapter(
        resolve_endpoints("anthropic", "https://host.test"),
        "sk-ant-test",
        client,
    )
    result = await adapter.generate_json(
        StructuredRequest(
            model="claude-test",
            system=STABLE_SYSTEM_RULES,
            prompt_prefix=build_prompt_prefix("项目规则", "本次规则"),
            prompt="\n\n待分析内容\n正文",
            output_type=AnalysisBatchResult,
            cache_system=True,
            cache_prompt_prefix=True,
            temperature=0,
        )
    )
    await client.aclose()

    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert captured["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert result.cache_usage_reported is False


class FakeAnalysisAdapter:
    def __init__(self, calls: list[StructuredRequest]):
        self.calls = calls

    async def generate_json(self, request: StructuredRequest):
        self.calls.append(request)
        block_ids = [
            line.removeprefix("BLOCK_ID: ")
            for line in request.prompt.splitlines()
            if line.startswith("BLOCK_ID: ")
        ]
        result = AnalysisBatchResult(
            candidates=[
                KeyPointCandidate(
                    title="第一章公式",
                    explanation="公式说明",
                    importance="core",
                    source_block_ids=block_ids,
                    evidence_quotes=["公式说明"],
                    rationale="项目提示要求优先公式",
                )
            ],
            source_questions=[],
        )
        return ProviderResult(value=result, model_id=request.model)


class FailingAnalysisAdapter:
    async def generate_json(self, _request: StructuredRequest):
        raise RuntimeError("provider failed")


def seed_analysis_data(engine):
    with Session(engine) as session:
        project = ReviewProject(name="期末复习", importance_prompt="优先公式")
        session.add(project)
        session.flush()
        provider = AIProviderProfile(
            name="第三方服务",
            protocol="anthropic",
            base_url="https://provider.test/v1",
            enabled=True,
            credential_generation=3,
        )
        session.add(provider)
        session.flush()
        model = ModelProfile(
            provider_id=provider.id,
            model_id="review-model",
            display_name="Review Model",
            text_status="passed",
            structured_status="passed",
            vision_status="passed",
        )
        session.add(model)
        document = SourceDocument(
            project_id=project.id,
            original_name="review.md",
            stored_name="sources/review/source.md",
            extension=".md",
            media_type="text/markdown",
            byte_size=10,
            sha256="source-sha",
            source_kind="knowledge",
            parse_status="ready",
            parser_version="1",
        )
        session.add(document)
        session.flush()
        blocks = [
            make_block(
                "heading-a", document_id=document.id, ordinal=0, kind="heading", text="第一章"
            ),
            make_block(
                "paragraph-a", document_id=document.id, ordinal=1, kind="paragraph", text="公式说明"
            ),
        ]
        session.add_all(blocks)
        session.commit()
        return project.id, provider.id, model.id, [block.id for block in blocks]


def test_worker_uses_success_cache_across_new_runs_and_process_instances(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    project_id, provider_id, model_profile_id, block_ids = seed_analysis_data(engine)
    secrets = MemorySecretStore()
    secrets.set(credential_key(provider_id), "private-key")
    calls: list[StructuredRequest] = []

    def adapter_factory(profile, api_key):
        assert profile.protocol == "anthropic"
        assert profile.base_url == "https://provider.test/v1"
        assert api_key == "private-key"
        return FakeAnalysisAdapter(calls)

    with Session(engine) as session:
        first_run, _job = schedule_analysis(
            session,
            project_id=project_id,
            selected_block_ids=block_ids,
            provider_id=provider_id,
            model_profile_id=model_profile_id,
            run_override="只看第一章",
            parameters={"temperature": 0},
        )
    first_handler = AnalysisWorkerHandler(engine, tmp_path / "Runtime", secrets, adapter_factory)
    first_handler({"run_id": first_run.id})

    with Session(engine) as session:
        first_batch = session.exec(
            select(AnalysisBatch).where(AnalysisBatch.run_id == first_run.id)
        ).one()
        assert session.get(AnalysisRun, first_run.id).status == "succeeded"
        assert first_batch.cache_status == "miss"

        second_run, _job = schedule_analysis(
            session,
            project_id=project_id,
            selected_block_ids=block_ids,
            provider_id=provider_id,
            model_profile_id=model_profile_id,
            run_override="只看第一章",
            parameters={"temperature": 0},
        )

    restarted_handler = AnalysisWorkerHandler(
        engine, tmp_path / "Runtime", secrets, adapter_factory
    )
    restarted_handler({"run_id": second_run.id})

    with Session(engine) as session:
        second_batch = session.exec(
            select(AnalysisBatch).where(AnalysisBatch.run_id == second_run.id)
        ).one()
    assert len(calls) == 1
    assert second_batch.cache_status == "hit"
    assert json.loads(second_batch.result_json)["candidates"][0]["title"] == "第一章公式"


def test_worker_sends_inline_source_images_to_a_vision_capable_model(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    project_id, provider_id, model_profile_id, block_ids = seed_analysis_data(engine)
    image_path = tmp_path / "data" / "sources" / "review" / "assets" / "image.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    with Session(engine) as session:
        image_block = session.get(SourceBlock, "paragraph-a")
        image_block.asset_path = "image.png"
        session.add(image_block)
        session.commit()
        run, _job = schedule_analysis(
            session,
            project_id=project_id,
            selected_block_ids=block_ids,
            provider_id=provider_id,
            model_profile_id=model_profile_id,
            run_override="",
            parameters={"temperature": 0},
        )
        run_id = run.id

    secrets = MemorySecretStore()
    secrets.set(credential_key(provider_id), "private-key")
    calls: list[StructuredRequest] = []
    handler = AnalysisWorkerHandler(
        engine,
        tmp_path / "Runtime",
        secrets,
        lambda _profile, _api_key: FakeAnalysisAdapter(calls),
        data_dir=tmp_path / "data",
    )
    handler({"run_id": run_id})

    assert len(calls) == 1
    assert calls[0].images[0].startswith("data:image/png;base64,")


def test_schedule_blocks_image_analysis_until_vision_probe_passes(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    project_id, provider_id, model_profile_id, block_ids = seed_analysis_data(engine)
    with Session(engine) as session:
        image_block = session.get(SourceBlock, "paragraph-a")
        image_block.asset_path = "image.png"
        model = session.get(ModelProfile, model_profile_id)
        model.vision_status = "untested"
        session.add(image_block)
        session.add(model)
        session.commit()

        with pytest.raises(AppError) as caught:
            schedule_analysis(
                session,
                project_id=project_id,
                selected_block_ids=block_ids,
                provider_id=provider_id,
                model_profile_id=model_profile_id,
                run_override="",
                parameters={"temperature": 0},
            )

    assert caught.value.code == "MODEL_VISION_NOT_VALIDATED"
    assert caught.value.action == "probe_model"


def test_terminal_worker_failure_marks_run_and_batch_failed_without_cache(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    project_id, provider_id, model_profile_id, block_ids = seed_analysis_data(engine)
    secrets = MemorySecretStore()
    secrets.set(credential_key(provider_id), "private-key")
    with Session(engine) as session:
        run, job = schedule_analysis(
            session,
            project_id=project_id,
            selected_block_ids=block_ids,
            provider_id=provider_id,
            model_profile_id=model_profile_id,
            run_override="",
            parameters={"temperature": 0},
        )
        run_id, job_id = run.id, job.id
        now = job.available_at.replace(tzinfo=UTC) + timedelta(seconds=1)

    handler = AnalysisWorkerHandler(
        engine,
        tmp_path / "Runtime",
        secrets,
        lambda _profile, _api_key: FailingAnalysisAdapter(),
    )
    worker = DurableWorker(
        engine,
        {"analysis_run": handler},
        worker_id="worker-test",
        retry_base_seconds=1,
    )
    assert worker.run_once(now=now)
    assert worker.run_once(now=now + timedelta(seconds=1))
    assert worker.run_once(now=now + timedelta(seconds=3))

    with Session(engine) as session:
        stored_run = session.get(AnalysisRun, run_id)
        stored_job = session.get(DurableJob, job_id)
        batch = session.exec(select(AnalysisBatch).where(AnalysisBatch.run_id == run_id)).one()
    assert stored_job.status == "failed"
    assert stored_run.status == "failed"
    assert batch.status == "failed"
    assert list((tmp_path / "Runtime" / "ai-cache").glob("[0-9a-f][0-9a-f]/*.json")) == []


def test_cancelled_analysis_marks_the_durable_job_cancelled(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    project_id, provider_id, model_profile_id, block_ids = seed_analysis_data(engine)
    secrets = MemorySecretStore()
    secrets.set(credential_key(provider_id), "private-key")
    with Session(engine) as session:
        run, job = schedule_analysis(
            session,
            project_id=project_id,
            selected_block_ids=block_ids,
            provider_id=provider_id,
            model_profile_id=model_profile_id,
            run_override="",
            parameters={"temperature": 0},
        )
        run_id, job_id = run.id, job.id
        now = job.available_at.replace(tzinfo=UTC) + timedelta(seconds=1)
        request_run_cancellation(session, run_id)

    handler = AnalysisWorkerHandler(
        engine,
        tmp_path / "Runtime",
        secrets,
        lambda _profile, _api_key: FakeAnalysisAdapter([]),
    )
    worker = DurableWorker(engine, {"analysis_run": handler}, worker_id="worker-test")
    assert worker.run_once(now=now)

    with Session(engine) as session:
        assert session.get(AnalysisRun, run_id).status == "cancelled"
        assert session.get(DurableJob, job_id).status == "cancelled"
