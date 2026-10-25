from dataclasses import dataclass
import heapq
import networkx as nx
from app.config import get_settings
from app.roadmap.retention import retention_penalty

@dataclass(frozen=True)
class TopicState:
    mastery: float
    last_updated: object | None = None
    estimated_minutes: int = 30

def normalized_time(minutes: int, max_minutes: int) -> float:
    return min(1.0, max(0.0, minutes / max(1, max_minutes)))

def objective_breakdown(state: TopicState, max_minutes: int):
    return {
        'mastery_deficit': max(0.0, min(1.0, 1 - state.mastery)),
        'retention_penalty': retention_penalty(state.last_updated),
        'time_cost': normalized_time(state.estimated_minutes, max_minutes),
    }

def weighted_cost(breakdown: dict) -> float:
    settings = get_settings()
    return settings.w1 * breakdown['mastery_deficit'] + settings.w2 * breakdown['retention_penalty'] + settings.w3 * breakdown['time_cost']

def admissible_heuristic(graph: nx.DiGraph, node: str, target: str, mastery: dict[str, float]) -> float:
    """Return the spec's admissible h(n): remaining mastery deficits only."""
    if node == target:
        return 0.0
    try:
        remaining = nx.ancestors(graph, target) - nx.ancestors(graph, node)
        remaining.add(target)
        remaining.discard(node)
        return sum(max(0.0, 1 - mastery.get(topic_id, 0.3)) for topic_id in remaining)
    except nx.NetworkXError:
        return 0.0

def _topological_prerequisites(graph: nx.DiGraph, target: str) -> list[str]:
    required = nx.ancestors(graph, target) | {target}
    return [node for node in nx.topological_sort(graph) if node in required]

def _astar_path(graph: nx.DiGraph, target: str, mastery: dict[str, float], states: dict[str, TopicState], max_minutes: int, start_node: str | None = None, trace: list[dict] | None = None) -> list[str]:
    """Search from a KST root to target with f(n)=g(n)+h(n)."""
    required = nx.ancestors(graph, target) | {target}
    if start_node is not None:
        if start_node not in graph or target not in nx.descendants(graph, start_node) | {start_node}:
            if trace is not None: trace.append({'type':'unreachable','start':start_node,'target':target,'message':'No directed prerequisite path exists from the selected start to target.'})
            return []
        required = (required & nx.descendants(graph, start_node)) | {start_node}
        roots = [start_node]
    else:
        roots = [node for node in required if not (set(graph.predecessors(node)) & required)]
    frontier = []
    counter = 0
    for root in roots:
        g_score = weighted_cost(objective_breakdown(states[root], max_minutes))
        heapq.heappush(frontier, (g_score + admissible_heuristic(graph, root, target, mastery), g_score, counter, root, (root,)))
        counter += 1
    if trace is not None:
        trace.append({'type':'initialized','start_nodes':roots,'target':target,'open_after':[{'topic_id':e[3],'f':e[0],'g':e[1]} for e in sorted(frontier)],'closed_after':[]})
    best_g: dict[str, float] = {}
    closed: set[str] = set()
    while frontier:
        frontier_before = sorted([{'topic_id':entry[3], 'f':entry[0], 'g':entry[1]} for entry in frontier], key=lambda entry:(entry['f'],entry['g'],entry['topic_id'])) if trace is not None else []
        f_score, g_score, _, node, path = heapq.heappop(frontier)
        event = {'type':'expand','step':len([e for e in trace if e.get('type') == 'expand']) + 1 if trace is not None else 0,'current_node':node,'g':g_score,'h':f_score-g_score,'f':f_score,'open_before':frontier_before,'closed_before':sorted(closed),'candidates':[]}
        if node == target:
            if trace is not None:
                event.update({'selected':'target','target_reached':True,'search_path':list(path),'open_after':[{'topic_id':e[3],'f':e[0],'g':e[1]} for e in sorted(frontier)],'closed_after':sorted(closed)})
                trace.append(event)
            return list(path)
        if g_score >= best_g.get(node, float('inf')):
            if trace is not None:
                event.update({'selected':'stale_entry_skipped','target_reached':False,'open_after':[{'topic_id':e[3],'f':e[0],'g':e[1]} for e in sorted(frontier)],'closed_after':sorted(closed)})
                trace.append(event)
            continue
        best_g[node] = g_score
        closed.add(node)
        for successor in graph.successors(node):
            if successor not in required:
                if trace is not None: event['candidates'].append({'topic_id':successor,'eligible':False,'reason':'outside the target prerequisite set'})
                continue
            if successor in path:
                if trace is not None: event['candidates'].append({'topic_id':successor,'eligible':False,'reason':'already in this path'})
                continue
            next_g = g_score + weighted_cost(objective_breakdown(states[successor], max_minutes))
            next_h = admissible_heuristic(graph, successor, target, mastery)
            next_f = next_g + next_h
            heapq.heappush(frontier, (next_f, next_g, counter, successor, path + (successor,)))
            if trace is not None: event['candidates'].append({'topic_id':successor,'eligible':True,'g':next_g,'h':next_h,'f':next_f,'selected_for_frontier':True})
            counter += 1
        if trace is not None:
            event.update({'selected':'expand_successors','target_reached':False,'open_after':[{'topic_id':e[3],'f':e[0],'g':e[1]} for e in sorted(frontier)],'closed_after':sorted(closed)})
            trace.append(event)
    if trace is not None: trace.append({'type':'unreachable','start':start_node,'target':target,'message':'Search frontier exhausted before the target was reached.'})
    if start_node is not None:
        return []
    return _topological_prerequisites(graph, target)

def generate_roadmap(graph: nx.DiGraph, mastery: dict[str, float], states: dict[str, TopicState], target: str | None = None, start_node: str | None = None, trace: list[dict] | None = None) -> list[str]:
    if not graph.nodes:
        return []
    if target is None:
        candidates = [node for node in graph.nodes if mastery.get(node, 0.3) < 0.8]
        target = min(candidates or list(graph.nodes), key=lambda node: mastery.get(node, 0.3))
    if target not in graph:
        raise ValueError('target topic is not in the KST')
    if start_node is not None and start_node not in graph:
        raise ValueError('start topic is not in the KST')
    required_order = _topological_prerequisites(graph, target)
    if start_node is not None:
        if target not in nx.descendants(graph, start_node) | {start_node}:
            if trace is not None: trace.append({'type':'unreachable','start':start_node,'target':target,'message':'No directed prerequisite path exists from the selected start to target.'})
            return []
        required_order = [node for node in required_order if node == start_node or node in nx.descendants(graph, start_node)]
    max_minutes = max((states[node].estimated_minutes for node in graph.nodes), default=60)
    best_path = _astar_path(graph, target, mastery, states, max_minutes, start_node, trace)
    if start_node is not None and not best_path:
        return []
    path_rank = {node: index for index, node in enumerate(best_path)}
    # A branched target needs all unmastered prerequisites. The A* path is used
    # as the priority spine; remaining branches retain DAG topological order.
    ordered = sorted(required_order, key=lambda node: (path_rank.get(node, len(best_path) + required_order.index(node)), required_order.index(node)))
    return [node for node in ordered if mastery.get(node, 0.3) < 0.85] or [target]
