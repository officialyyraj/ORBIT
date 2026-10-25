from fastapi.testclient import TestClient
from app.main import app

def test_seeded_full_flow():
    client = TestClient(app)
    login = client.post('/api/v1/auth/login', json={'email': 'demo@orbit.dev', 'password': 'orbit-demo'})
    assert login.status_code == 200
    token = login.json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    before = client.get('/api/v1/mastery/me', headers=headers)
    assert before.status_code == 200
    diagnostic = client.get('/api/v1/quiz/diagnostic', headers=headers)
    assert diagnostic.status_code == 200 and diagnostic.json()['questions']
    question = diagnostic.json()['questions'][0]
    answer = client.post('/api/v1/quiz/response', headers=headers, json={'question_id': question['id'], 'selected_choice_index': 0})
    assert answer.status_code == 200
    assert answer.json()['updated_mastery']['source'] == 'bkt'
    after = client.get('/api/v1/mastery/me', headers=headers)
    assert after.status_code == 200
    assert len(after.json()['estimates']) == len(before.json()['estimates'])
    roadmap = client.get('/api/v1/roadmap/me', headers=headers)
    assert roadmap.status_code == 200 and roadmap.json()['mode'] == 'weighted'
    assert isinstance(roadmap.json()['path'], list)
