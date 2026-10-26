from fastapi.testclient import TestClient
from app.main import app
import uuid

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


def test_diagnostic_is_track_scoped_bounded_and_reports_unknown_tracks():
    client = TestClient(app)
    auth = client.post(
        '/api/v1/auth/signup',
        json={'email': f'diagnostic-{uuid.uuid4().hex}@example.test', 'password': 'diagnostic-test-password'},
    )
    assert auth.status_code == 201
    headers = {'Authorization': f"Bearer {auth.json()['token']}"}
    library = client.get('/api/v1/content/library').json()['tracks']
    selected_track = next(track for track in library if track['id'] == 'python')
    expected_topic_ids = {
        topic['id']
        for module in selected_track['modules']
        for topic in module['topics']
    }

    scoped = client.get('/api/v1/quiz/diagnostic?track_id=python', headers=headers)
    assert scoped.status_code == 200
    assert {question['topic_id'] for question in scoped.json()['questions']} == expected_topic_ids

    unscoped = client.get('/api/v1/quiz/diagnostic', headers=headers)
    assert unscoped.status_code == 200
    assert 0 < len(unscoped.json()['questions']) <= 12

    unknown = client.get('/api/v1/quiz/diagnostic?track_id=missing-track', headers=headers)
    assert unknown.status_code == 404
    assert unknown.json()['error']['code'] == 'not_found'


def test_default_roadmap_target_is_track_scoped_and_deterministic():
    client = TestClient(app)
    auth = client.post(
        '/api/v1/auth/signup',
        json={'email': f'roadmap-track-{uuid.uuid4().hex}@example.test', 'password': 'roadmap-test-password'},
    )
    assert auth.status_code == 201
    headers = {'Authorization': f"Bearer {auth.json()['token']}"}

    first = client.get('/api/v1/roadmap/me?track_id=python', headers=headers)
    repeated = client.get('/api/v1/roadmap/me?track_id=python', headers=headers)
    web = client.get('/api/v1/roadmap/me?track_id=web-development', headers=headers)
    assert first.status_code == repeated.status_code == web.status_code == 200
    python_target = first.json()['path'][-1]['topic_id']
    web_target = web.json()['path'][-1]['topic_id']
    tracks = client.get('/api/v1/content/library').json()['tracks']
    topic_track = {
        topic['id']: track['id']
        for track in tracks
        for module in track['modules']
        for topic in module['topics']
    }

    assert [node['topic_id'] for node in first.json()['path']] == [
        node['topic_id'] for node in repeated.json()['path']
    ]
    assert topic_track[python_target] == 'python'
    assert topic_track[web_target] == 'web-development'
    assert python_target != web_target
