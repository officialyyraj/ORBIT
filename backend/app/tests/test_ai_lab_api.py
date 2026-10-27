import uuid
from sqlalchemy import func, select
from app.db.models import MasteryEstimate, QuizResponse
from app.db.session import SessionLocal
from app.mastery.bkt import default_parameters, update_mastery


def test_ai_lab_uses_real_graph_bkt_astar_and_keeps_demo_stateless(client):
    email = f"ai-lab-{uuid.uuid4().hex}@example.test"
    auth = client.post('/api/v1/auth/signup', json={'email':email,'password':'lab-test-password'})
    assert auth.status_code == 201
    headers = {'Authorization':f"Bearer {auth.json()['token']}"}

    graph_response = client.get('/api/v1/ai-lab/graph', headers=headers)
    assert graph_response.status_code == 200
    graph = graph_response.json()
    assert graph['diagnostics']['formal_knowledge_space_claim'] is False
    py_values = next(node for node in graph['nodes'] if node['slug'] == 'py-values')
    assert py_values['mastery_probability'] is None
    assert py_values['mastery_status'] == 'unknown'

    params = default_parameters()
    for correct in (True, False):
        response = client.post('/api/v1/ai-lab/bkt/step', headers=headers, json={'prior_mastery':.3,'correct':correct})
        assert response.status_code == 200
        trace = response.json()['trace']
        assert abs(trace['final_mastery'] - update_mastery(.3,correct,params)) < 1e-10
        assert abs(trace['observation_posterior'] + (1-trace['observation_posterior'])*params.p_transit - trace['final_mastery']) < 1e-10
        assert response.json()['persisted'] is False

    search = client.post('/api/v1/ai-lab/search', headers=headers, json={'start_topic_id':py_values['id'],'target_topic_id':py_values['id']})
    assert search.status_code == 200
    assert search.json()['persisted'] is False
    assert search.json()['search_path'] == [py_values['id']]

    with SessionLocal() as db:
        user_id = auth.json()['user_id']
        responses_before = db.scalar(select(func.count()).select_from(QuizResponse).where(QuizResponse.student_id == user_id))
        mastery_before = db.scalar(select(func.count()).select_from(MasteryEstimate).where(MasteryEstimate.student_id == user_id))

    demo = client.post('/api/v1/ai-lab/demo/step', headers=headers, json={'topic_id':py_values['id'],'start_topic_id':py_values['id'],'target_topic_id':py_values['id'],'correct':True,'mastery':{}})
    assert demo.status_code == 200
    result = demo.json()
    assert result['persisted'] is False and result['mode'] == 'synthetic_integrated_demo'
    assert abs(result['bkt']['final_mastery'] - update_mastery(params.p_init,True,params)) < 1e-10
    assert result['search_path'] == [py_values['id']]

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(QuizResponse).where(QuizResponse.student_id == auth.json()['user_id'])) == responses_before
        assert db.scalar(select(func.count()).select_from(MasteryEstimate).where(MasteryEstimate.student_id == auth.json()['user_id'])) == mastery_before


def test_ai_lab_routes_require_authentication_and_validate_probabilities(client):
    assert client.get('/api/v1/ai-lab/graph').status_code == 401
    auth = client.post('/api/v1/auth/signup', json={'email':f"ai-lab-invalid-{uuid.uuid4().hex}@example.test",'password':'lab-test-password'})
    headers = {'Authorization':f"Bearer {auth.json()['token']}"}
    assert client.post('/api/v1/ai-lab/bkt/step', headers=headers, json={'prior_mastery':1.1,'correct':True}).status_code == 422


def test_integrated_demo_scores_a_published_choice_without_persisting_it(client):
    email = f"ai-lab-question-{uuid.uuid4().hex}@example.test"
    auth = client.post('/api/v1/auth/signup', json={'email':email,'password':'lab-test-password'})
    headers = {'Authorization':f"Bearer {auth.json()['token']}"}
    with SessionLocal() as db:
        from app.db.models import Question, Topic
        topic = db.scalar(select(Topic).where(Topic.slug == 'py-values'))
        question = db.scalar(select(Question).where(Question.topic_id == topic.id, Question.review_status == 'approved'))
        topic_id, question_id, correct_index, choice_count = topic.id, question.id, question.correct_choice_index, len(question.choices)
        user_id = auth.json()['user_id']
        responses_before = db.scalar(select(func.count()).select_from(QuizResponse).where(QuizResponse.student_id == user_id))
        mastery_before = db.scalar(select(func.count()).select_from(MasteryEstimate).where(MasteryEstimate.student_id == user_id))
    selected = (correct_index + 1) % choice_count
    response = client.post('/api/v1/ai-lab/demo/step', headers=headers, json={'topic_id':topic_id,'question_id':question_id,'selected_choice_index':selected,'start_topic_id':topic_id,'target_topic_id':topic_id,'mastery':{}})
    assert response.status_code == 200
    result = response.json()
    assert result['assessment']['correct'] is False
    assert result['bkt']['observed_response'] == 'incorrect'
    assert result['persisted'] is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(QuizResponse).where(QuizResponse.student_id == user_id)) == responses_before
        assert db.scalar(select(func.count()).select_from(MasteryEstimate).where(MasteryEstimate.student_id == user_id)) == mastery_before
