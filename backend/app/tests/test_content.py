from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
import networkx as nx
import pytest
from app.content import import_library, validate_library
from app.content_library import build_library
from app.db.models import Base, MasteryEstimate, Module, Question, Topic, TopicEdge, Track, User
from app.kst.seed_data import LEGACY_MODULE_ID_BY_NAME, connect_legacy_topics, seed
from app.roadmap.astar import TopicState, generate_roadmap


def test_library_batch_has_structured_topics_and_eight_questions_each():
    data = build_library()
    assert len(data['tracks']) == 6
    assert len(data['topics']) == 89
    assert all(8 <= len(topic['questions']) <= 12 for topic in data['topics'])
    assert validate_library(data) == []


def test_seed_literal_references_exist_in_library_definitions():
    data = build_library()
    module_ids = {module['id'] for module in data['modules']}
    topic_slugs = {topic['slug'] for topic in data['topics']}

    assert set(LEGACY_MODULE_ID_BY_NAME.values()) <= module_ids
    assert 'cs-graphs-overview' in topic_slugs


def test_cross_track_prerequisites_form_a_connected_dag():
    data = build_library()
    track_by_module = {module['id']: module['track_id'] for module in data['modules']}
    track_by_slug = {topic['slug']: track_by_module[topic['module_id']] for topic in data['topics']}
    graph = nx.DiGraph()
    graph.add_nodes_from(track_by_slug)
    edges = [
        (prerequisite, topic['slug'])
        for topic in data['topics']
        for prerequisite in topic.get('prerequisites', [])
    ]
    graph.add_edges_from(edges)

    assert nx.is_directed_acyclic_graph(graph)
    assert any(track_by_slug[left] != track_by_slug[right] for left, right in edges)
    assert nx.number_weakly_connected_components(graph) < 7


def test_python_roadmap_includes_low_mastery_programming_foundations():
    data = build_library()
    graph = nx.DiGraph()
    graph.add_nodes_from(topic['slug'] for topic in data['topics'])
    graph.add_edges_from(
        (prerequisite, topic['slug'])
        for topic in data['topics']
        for prerequisite in topic.get('prerequisites', [])
    )
    mastery = {topic: 0.1 for topic in graph}
    states = {topic: TopicState(mastery=0.1, estimated_minutes=30) for topic in graph}

    path = generate_roadmap(graph, mastery, states, 'py-values')

    assert path.index('pf-variables') < path.index('py-values')


def test_import_is_idempotent_and_preserves_learner_records():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        data = build_library()
        first = import_library(session, data)
        edge = session.scalar(
            select(TopicEdge)
            .join(Topic, Topic.id == TopicEdge.prerequisite_id)
            .where(Topic.slug == 'pf-variables')
        )
        edge.confidence_score = .42
        session.commit()
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
        assert edge.confidence_score == .42
    finally:
        session.close(); engine.dispose()


def test_seed_and_library_import_are_idempotent_without_deleting_legacy_history():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        data = build_library()
        seed(session)
        import_library(session, data)
        connect_legacy_topics(session)
        first_counts = (
            session.scalar(select(func.count()).select_from(Topic)),
            session.scalar(select(func.count()).select_from(TopicEdge)),
        )
        legacy = session.scalar(select(Topic).where(Topic.name == 'Machine Learning'))
        assert legacy.module_id is not None
        assert 'legacy seed' in legacy.provenance
        assert {
            topic.name: topic.module_id
            for topic in session.scalars(
                select(Topic).where(Topic.name.in_([
                    'Python Syntax', 'Functions', 'Recursion', 'Trees', 'Graphs', 'Machine Learning',
                ]))
            )
        } == {
            'Python Syntax': 'py-core',
            'Functions': 'py-core',
            'Recursion': 'cs-recursion',
            'Trees': 'cs-structures',
            'Graphs': 'cs-graphs',
            'Machine Learning': 'cs-systems',
        }

        seed(session)
        import_library(session, data)
        connect_legacy_topics(session)
        second_counts = (
            session.scalar(select(func.count()).select_from(Topic)),
            session.scalar(select(func.count()).select_from(TopicEdge)),
        )

        assert first_counts == second_counts
        assert first_counts[0] == 95
    finally:
        session.close(); engine.dispose()


def test_fresh_seed_references_all_exist_with_sqlite_foreign_keys_enabled():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        seed(session)
        import_library(session, build_library())
        connect_legacy_topics(session)

        assert session.connection().exec_driver_sql('PRAGMA foreign_keys').scalar_one() == 1
        missing_topic_modules = session.scalar(
            select(func.count())
            .select_from(Topic)
            .outerjoin(Module, Topic.module_id == Module.id)
            .where(Topic.module_id.is_not(None), Module.id.is_(None))
        )
        missing_module_tracks = session.scalar(
            select(func.count())
            .select_from(Module)
            .outerjoin(Track, Module.track_id == Track.id)
            .where(Track.id.is_(None))
        )
        assert missing_topic_modules == 0
        assert missing_module_tracks == 0
    finally:
        session.close()
        engine.dispose()


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


def test_library_and_lesson_api_integrate_with_existing_quiz_flow(client):
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
