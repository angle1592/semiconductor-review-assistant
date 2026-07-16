from fastapi.testclient import TestClient

from app.providers.credentials import MemorySecretStore
from app.main import create_app


def test_review_project_lifecycle(tmp_path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            json={
                "name": "期末总复习",
                "description": "材料综合复习",
                "importance_prompt": "优先公式与易错点",
            },
        )

        assert created.status_code == 201
        project = created.json()
        assert project["name"] == "期末总复习"
        assert project["description"] == "材料综合复习"
        assert project["importance_prompt"] == "优先公式与易错点"
        assert project["created_at"]
        assert project["updated_at"]
        assert client.get("/api/projects").json() == [project]
        assert client.get(f"/api/projects/{project['id']}").json() == project

        updated = client.patch(
            f"/api/projects/{project['id']}",
            json={"name": "资格考试总复习", "importance_prompt": "优先法规和易混点"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "资格考试总复习"
        assert updated.json()["importance_prompt"] == "优先法规和易混点"

        assert client.delete(f"/api/projects/{project['id']}").status_code == 204
        assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_review_project_validates_name_and_missing_project(tmp_path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    with TestClient(app) as client:
        invalid = client.post("/api/projects", json={"name": ""})
        missing = client.get("/api/projects/missing")

    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"
    assert missing.json()["request_id"]
