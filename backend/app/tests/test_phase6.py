from types import SimpleNamespace
import networkx as nx
from fastapi.testclient import TestClient
from app.main import app
from app.mastery.dkt import DKTStrategy
from app.refinement import edge_confidence
from app.roadmap.astar import TopicState
from app.roadmap.pareto import generate_pareto_paths
from app.db.session import SessionLocal
from app.db.models import Topic, TopicEdge
from sqlalchemy import select


def test_edge_confidence_uses_conditional_accuracy(monkeypatch):
    edge = SimpleNamespace(edge_id='edge', id='edge', prerequisite_id='a', topic_id='b', confidence_score=1.0)
    monkeypatch.setattr(edge_confidence, '_response_map', lambda db: {
        's1': {'a': True, 'b': True},
        's2': {'a': True, 'b': True},
        's3': {'a': False, 'b': False},
        's4': {'a': False, 'b': True},
    })
    result = edge_confidence.compute_edge_confidence(object(), edge)
    assert result.positive_gap == 0.5
    assert result.confidence_score > 0.5
    assert result.sample_count == 4


def test_pareto_mode_returns_labeled_candidates():
    graph = nx.DiGraph([('a', 'b'), ('b', 'c'), ('a', 'c')])
    states = {node: TopicState(mastery=0.2, estimated_minutes=20 + index * 10) for index, node in enumerate(graph.nodes)}
    results = generate_pareto_paths(graph, {node: state.mastery for node, state in states.items()}, states, 'c')
    assert results
    assert {item[0] for item in results} <= {'Fastest', 'Best retention', 'Balanced'}
    assert all(item[2].path for item in results)


def test_dkt_initializes_from_kst_and_round_trips_checkpoint(tmp_path):
    with SessionLocal() as db:
        model = DKTStrategy()
        model.initialize_from_kst(db)
        assert len(model.topic_ids) == len(db.scalars(select(Topic)).all())
        assert model.embeddings.shape[0] == len(model.topic_ids)
        path = tmp_path / 'dkt.json'
        model.save(str(path))
        loaded = DKTStrategy(str(path))
        assert loaded.topic_ids == model.topic_ids
        assert loaded.embeddings.shape == model.embeddings.shape


def test_phase6_admin_and_pareto_api():
    client = TestClient(app)
    login = client.post('/api/v1/auth/login', json={'email': 'demo@orbit.dev', 'password': 'orbit-demo'})
    token = login.json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    pareto = client.get('/api/v1/roadmap/me?mode=pareto', headers=headers)
    assert pareto.status_code == 200
    assert pareto.json()['mode'] == 'pareto'
    assert pareto.json()['paths']
    review = client.get('/api/v1/admin/edges/low-confidence', headers=headers)
    assert review.status_code == 200
    refine = client.post('/api/v1/kst/edges/refine', headers=headers)
    assert refine.status_code == 200
    assert refine.json()['updated_edges'] >= 1
