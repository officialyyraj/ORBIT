from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
import pytest
from app.content import import_library, validate_library
from app.content_library import build_library
from app.db.models import Base, MasteryEstimate, Question, Topic, Track, User


def test_library_batch_has_structured_topics_and_eight_questions_each():
    data = build_library()
    assert len(data['tracks']) == 6
    assert len(data['topics']) == 89
    assert all(8 <= len(topic['questions']) <= 12 for topic in data['topics'])
    assert validate_library(data) == []


def test_import_is_idempotent_and_preserves_learner_records():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        data = build_library()
        first = import_library(session, data)
        student = User(email='learner@example.test', password_hash='not-a-real-hash')
        session.add(student); session.flush()
        topic = session.scalar(select(Topic).where(Topic.slug == 'py-values'))
        session.add(MasteryEstimate(student_id=student.id, topic_id=topic.id, p_mastery=.72))
        session.commit()
        second = import_library(session, data)
        assert first['topics'] == second['topics'] == 89
        assert session.scalar(select(func.count()).select_from(Topic)) == 89
        assert session.scalar(select(func.count()).select_from(Question)) == 712
        assert session.scalar(select(func.count()).select_from(Track)) == 6
        assert session.scalar(select(MasteryEstimate).where(MasteryEstimate.student_id == student.id)).p_mastery == .72
    finally:
        session.close(); engine.dispose()


def test_validator_rejects_near_duplicate_question_prompts():
    data = build_library()
    data['topics'][0]['questions'][0]['prompt'] = 'Explain this carefully using the relevant concept and justify the answer in a concrete example.'
    data['topics'][0]['questions'][1]['prompt'] = 'Explain this carefully using the relevant concept and justify the answer in a concrete example now.'
    errors = validate_library(data)
    assert any('near-duplicate question prompts' in error for error in errors)


def test_validator_rejects_prerequisite_cycles_and_missing_questions():
    data = build_library()
    data['topics'][0]['prerequisites'] = [data['topics'][1]['slug']]
    data['topics'][1]['prerequisites'] = [data['topics'][0]['slug']]
    data['topics'][2]['questions'] = []
    errors = validate_library(data)
    assert 'prerequisite graph contains a cycle' in errors
    assert any('expected 8-12 questions, got 0' in error for error in errors)


def test_import_rejects_invalid_batch_before_writing():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        data = build_library(); data['topics'][0]['questions'][0]['correct'] = 500
        with pytest.raises(ValueError, match='Content validation failed'):
            import_library(session, data)
        assert session.scalar(select(func.count()).select_from(Track)) == 0
    finally:
        session.close(); engine.dispose()


def test_library_and_lesson_api_integrate_with_existing_quiz_flow():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    library = client.get('/api/v1/content/library')
    assert library.status_code == 200
    tracks = library.json()['tracks']
    assert len(tracks) == 6
    topic = next(t for track in tracks for module in track['modules'] for t in module['topics'] if t['slug'] == 'py-values')
    lesson = client.get('/api/v1/content/topics/py-values')
    assert lesson.status_code == 200 and lesson.json()['content']['explanation']
    signup = client.post('/api/v1/auth/signup', json={'email':'content-integration@example.test','password':'test-password-123'})
    if signup.status_code == 400:
        signup = client.post('/api/v1/auth/login', json={'email':'content-integration@example.test','password':'test-password-123'})
    assert signup.status_code in (200, 201)
    headers = {'Authorization':f"Bearer {signup.json()['token']}"}
    quiz = client.get(f"/api/v1/quiz/topic/{topic['id']}", headers=headers)
    assert quiz.status_code == 200 and len(quiz.json()['questions']) == 8
    answer = client.post('/api/v1/quiz/response', headers=headers, json={'question_id':quiz.json()['questions'][0]['id'],'selected_choice_index':0})
    assert answer.status_code == 200 and answer.json()['explanation']
