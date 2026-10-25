from dataclasses import dataclass
import networkx as nx
from app.config import get_settings
from app.roadmap.astar import TopicState, objective_breakdown

@dataclass(frozen=True)
class PathScore:
    path: tuple[str, ...]
    mastery: float
    retention: float
    time: float


def _dominates(left: PathScore, right: PathScore) -> bool:
    no_worse = left.mastery <= right.mastery and left.retention <= right.retention and left.time <= right.time
    strictly_better = left.mastery < right.mastery or left.retention < right.retention or left.time < right.time
    return no_worse and strictly_better


def _candidate_paths(graph: nx.DiGraph, target: str, max_paths: int = 128) -> list[tuple[str, ...]]:
    required = nx.ancestors(graph, target) | {target}
    roots = [node for node in required if not (set(graph.predecessors(node)) & required)]
    candidates: list[tuple[str, ...]] = []
    for root in roots:
        for path in nx.all_simple_paths(graph, root, target, cutoff=len(required)):
            if all(node in required for node in path):
                candidates.append(tuple(path))
            if len(candidates) >= max_paths:
                return candidates
    if not candidates:
        return [tuple(node for node in nx.topological_sort(graph) if node in required)]
    return candidates


def score_path(path: tuple[str, ...], states: dict[str, TopicState], max_minutes: int) -> PathScore:
    breakdowns = [objective_breakdown(states[node], max_minutes) for node in path]
    return PathScore(path, sum(item['mastery_deficit'] for item in breakdowns), sum(item['retention_penalty'] for item in breakdowns), sum(item['time_cost'] for item in breakdowns))


def pareto_frontier(scores: list[PathScore]) -> list[PathScore]:
    return [candidate for candidate in scores if not any(_dominates(other, candidate) for other in scores if other != candidate)]


def generate_pareto_paths(graph: nx.DiGraph, mastery: dict[str, float], states: dict[str, TopicState], target: str | None = None) -> list[tuple[str, tuple[str, ...], PathScore]]:
    if not graph.nodes:
        return []
    if target is None:
        candidates = [node for node in graph.nodes if mastery.get(node, 0.3) < 0.8]
        target = min(candidates or list(graph.nodes), key=lambda node: mastery.get(node, 0.3))
    if target not in graph:
        raise ValueError('target topic is not in the KST')
    max_minutes = max((states[node].estimated_minutes for node in graph.nodes), default=60)
    scores = [score_path(path, states, max_minutes) for path in _candidate_paths(graph, target)]
    frontier = pareto_frontier(scores) or scores
    settings = get_settings()
    fastest = min(frontier, key=lambda item: (item.time, item.mastery, item.retention))
    best_retention = min(frontier, key=lambda item: (item.retention, item.mastery, item.time))
    balanced = min(frontier, key=lambda item: settings.w1 * item.mastery + settings.w2 * item.retention + settings.w3 * item.time)
    return [('Fastest', fastest.path, fastest), ('Best retention', best_retention.path, best_retention), ('Balanced', balanced.path, balanced)]
