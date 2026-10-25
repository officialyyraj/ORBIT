from datetime import datetime, timedelta, timezone
import networkx as nx
from app.mastery.bkt import BKTParameters, update_mastery
from app.roadmap.retention import retention_penalty, retention_value
from app.roadmap.astar import TopicState, generate_roadmap

def test_bkt_correct_update_exact_formula():
    p = BKTParameters(.3, .1, .1, .2)
    value = update_mastery(.3, True, p)
    posterior = (.3 * .9) / ((.3 * .9) + (.7 * .2))
    expected = posterior + (1 - posterior) * .1
    assert abs(value - expected) < 1e-9

def test_bkt_incorrect_update_is_bounded():
    value = update_mastery(.7, False, BKTParameters(.3, .1, .1, .2))
    assert 0 <= value <= 1
    assert value < .7

def test_retention_decays_and_penalty_increases():
    now = datetime.now(timezone.utc)
    fresh = retention_value(now, now)
    old = retention_value(now - timedelta(days=28), now)
    assert fresh > old
    assert retention_penalty(now, now) == 0
    assert retention_penalty(now - timedelta(days=28), now) > 0

def test_roadmap_respects_prerequisite_order_and_prioritizes_gap():
    graph = nx.DiGraph([('a','b'),('b','c')])
    states = {n: TopicState(mastery=0.1 if n == 'b' else 0.3, estimated_minutes=30) for n in graph.nodes}
    path = generate_roadmap(graph, {n: s.mastery for n,s in states.items()}, states, 'c')
    assert path == ['a','b','c']

def test_astar_trace_preserves_default_production_route_and_reports_real_scores():
    graph = nx.DiGraph([('a','b'),('b','c')])
    mastery = {'a':.3,'b':.4,'c':.2}
    states = {n:TopicState(mastery=value,estimated_minutes=30) for n,value in mastery.items()}
    expected = generate_roadmap(graph, mastery, states, 'c')
    events = []
    actual = generate_roadmap(graph, mastery, states, 'c', trace=events)
    assert actual == expected == ['a','b','c']
    goal = next(item for item in events if item.get('target_reached'))
    assert goal['search_path'] == ['a','b','c']
    expansions = [item for item in events if item['type'] == 'expand']
    assert expansions
    assert all(abs(item['f'] - item['g'] - item['h']) < 1e-9 for item in expansions)
    assert all(abs(candidate['f'] - candidate['g'] - candidate['h']) < 1e-9 for item in expansions for candidate in item['candidates'] if candidate['eligible'])

def test_astar_explicit_start_reports_unreachable_without_fallback_path():
    graph = nx.DiGraph([('a','b'),('x','y')])
    mastery = {n:.3 for n in graph.nodes}
    states = {n:TopicState(mastery=.3,estimated_minutes=30) for n in graph.nodes}
    events = []
    assert generate_roadmap(graph, mastery, states, 'b', start_node='y', trace=events) == []
    assert events[0]['type'] == 'unreachable'
