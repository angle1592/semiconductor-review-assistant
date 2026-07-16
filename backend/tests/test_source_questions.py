import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.main import create_app
from app.providers.credentials import MemorySecretStore
from app.study.models import SourceQuestion
from app.study.service import materialize_run_source_questions
from tests.test_analysis_api import run_payload, seed_project_materials


def test_extracted_questions_deduplicate_edit_archive_and_restore(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, provider_id, model_id, block_ids = seed_project_materials(app)
    with TestClient(app) as client:
        created = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(provider_id, model_id, {"mode": "selected_blocks", "block_ids": block_ids}),
        ).json()
        with Session(app.state.database) as session:
            run = session.get(AnalysisRun, created["run_id"])
            batch = session.exec(select(AnalysisBatch).where(AnalysisBatch.run_id == run.id)).one()
            batch.status = "succeeded"
            batch.result_json = json.dumps({"candidates": [], "source_questions": [{"question": "什么是带隙？", "answer": "价带顶与导带底的能量差", "source_block_ids": ["paragraph-a"], "evidence_quotes": ["公式说明与易错点"]}]}, ensure_ascii=False)
            run.status = "succeeded"
            run.completed_batches = 1
            session.add(batch)
            session.add(run)
            session.commit()
            first = materialize_run_source_questions(session, run.id)
            second = materialize_run_source_questions(session, run.id)
            assert len(first) == len(second) == 1

        question = client.get(f"/api/projects/{project_id}/source-questions").json()[0]
        edited = client.patch(f"/api/source-questions/{question['id']}", json={"answer_text": "人工修订答案"})
        assert edited.json()["user_edited"] is True
        assert edited.json()["answer_text"] == "人工修订答案"
        archived = client.post(f"/api/source-questions/{question['id']}/archive")
        assert archived.json()["archived"] is True
        assert client.get(f"/api/projects/{project_id}/source-questions").json() == []
        restored = client.post(f"/api/source-questions/{question['id']}/restore")
        assert restored.json()["answer_text"] == "人工修订答案"
        with Session(app.state.database) as session:
            materialize_run_source_questions(session, created["run_id"])
            stored = session.get(SourceQuestion, question["id"])
            assert stored.answer_text == "人工修订答案"
        impact = client.get(f"/api/sources/{question['document_id']}/deletion-impact")
        assert impact.json()["source_questions"] == 1
        assert client.delete(f"/api/sources/{question['document_id']}").status_code == 200
        with Session(app.state.database) as session:
            assert session.get(SourceQuestion, question["id"]) is None
