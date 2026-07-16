import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import create_app
from app.mastery.models import MasteryRecord, StudyAttempt
from app.providers.credentials import MemorySecretStore
from tests.test_analysis_api import seed_project_materials


def test_attempts_are_append_only_and_rating_updates_one_record(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, *_rest, block_ids = seed_project_materials(app)
    with TestClient(app) as client:
        point = client.post(f"/api/projects/{project_id}/keypoints", json={"title": "带隙", "explanation": "定义", "importance": "core", "source_block_ids": block_ids, "evidence_quotes": []}).json()
        first = client.post(f"/api/projects/{project_id}/study-attempts", json={"mode": "outline", "item_type": "keypoint", "item_id": point["id"], "response": {"opened": True}, "self_rating": "learning"})
        second = client.post(f"/api/projects/{project_id}/study-attempts", json={"mode": "flashcards", "item_type": "keypoint", "item_id": point["id"], "self_rating": "familiar"})
        assert first.status_code == second.status_code == 201
        assert first.json()["correct"] is None
        assert second.json()["correct"] is None

        rated = client.put(f"/api/projects/{project_id}/mastery/keypoint/{point['id']}", json={"level": "mastered"})
        assert rated.status_code == 200
        assert rated.json()["level"] == "mastered"
        records = client.get(f"/api/projects/{project_id}/mastery", params={"level": "mastered", "target_type": "keypoint"}).json()
        assert len(records) == 1
        summary = client.get(f"/api/projects/{project_id}/mastery/summary").json()
        assert summary["total"] == 1
        assert summary["by_level"]["mastered"] == 1

    with Session(app.state.database) as session:
        assert len(session.exec(select(StudyAttempt)).all()) == 2
        assert len(session.exec(select(MasteryRecord)).all()) == 1
    with sqlite3.connect(tmp_path / "data" / "shiyao.db") as connection:
        attempt_columns = {row[1] for row in connection.execute("PRAGMA table_info(study_attempt)")}
        mastery_columns = {row[1] for row in connection.execute("PRAGMA table_info(mastery_record)")}
    forbidden = {"due_date", "exam_date", "streak", "daily_assignment"}
    assert not (attempt_columns | mastery_columns) & forbidden


def test_target_must_belong_to_project_and_project_delete_cascades_tracking(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    first_project, *_rest, block_ids = seed_project_materials(app)
    with TestClient(app) as client:
        second_project = client.post("/api/projects", json={"name": "其他项目"}).json()["id"]
        point = client.post(f"/api/projects/{first_project}/keypoints", json={"title": "定义", "explanation": "说明", "importance": "core", "source_block_ids": block_ids, "evidence_quotes": []}).json()
        invalid = client.post(f"/api/projects/{second_project}/study-attempts", json={"mode": "outline", "item_type": "keypoint", "item_id": point["id"]})
        assert invalid.status_code == 404
        client.post(f"/api/projects/{first_project}/study-attempts", json={"mode": "outline", "item_type": "keypoint", "item_id": point["id"], "self_rating": "learning"})
        assert client.delete(f"/api/projects/{first_project}").status_code == 200
    with Session(app.state.database) as session:
        assert session.exec(select(StudyAttempt)).all() == []
        assert session.exec(select(MasteryRecord)).all() == []
