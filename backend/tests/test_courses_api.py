from fastapi.testclient import TestClient

from app.main import create_app


def test_health_and_course_lifecycle(tmp_path):
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}

        created = client.post(
            "/api/courses", json={"title": "晶圆制造基础", "description": "培训第一阶段"}
        )
        assert created.status_code == 201
        course = created.json()

        listed = client.get("/api/courses")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == course["id"]


def test_errors_use_consistent_problem_shape(tmp_path):
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/courses/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["request_id"]
