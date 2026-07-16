from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_phase_one_review_project_story(tmp_path: Path):
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        ready = client.get('/ready')
        created = client.post(
            '/api/projects',
            json={
                'name': '资格考试总复习',
                'description': '汇总多份考试资料',
                'importance_prompt': '优先定义、公式与易错点',
            },
        )
        project_id = created.json()['id']
        listed = client.get('/api/projects')
        deleted = client.delete(f'/api/projects/{project_id}')
        after_delete = client.get('/api/projects')

    assert ready.status_code == 200
    assert ready.json()['checks']['database'] == 'ok'
    assert created.status_code == 201
    assert [project['id'] for project in listed.json()] == [project_id]
    assert deleted.status_code == 204
    assert after_delete.json() == []
