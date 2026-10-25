from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db.models import QuizResponse, Topic, TopicEdge

@dataclass(frozen=True)
class EdgeConfidenceResult:
    edge_id: str
    prerequisite_id: str
    topic_id: str
    confidence_score: float
    positive_gap: float
    sample_count: int


def _response_map(db: Session) -> dict[str, dict[str, bool]]:
    rows = db.scalars(select(QuizResponse).order_by(QuizResponse.responded_at, QuizResponse.id)).all()
    result: dict[str, dict[str, bool]] = {}
    for row in rows:
        result.setdefault(row.student_id, {})[row.topic_id] = row.correct
    return result


def compute_edge_confidence(db: Session, edge: TopicEdge) -> EdgeConfidenceResult:
    responses = _response_map(db)
    correct_given_prerequisite: list[bool] = []
    incorrect_given_prerequisite: list[bool] = []
    for student in responses.values():
        if edge.prerequisite_id not in student or edge.topic_id not in student:
            continue
        if student[edge.prerequisite_id]:
            correct_given_prerequisite.append(student[edge.topic_id])
        else:
            incorrect_given_prerequisite.append(student[edge.topic_id])
    p_correct = sum(correct_given_prerequisite) / len(correct_given_prerequisite) if correct_given_prerequisite else 0.0
    p_incorrect = sum(incorrect_given_prerequisite) / len(incorrect_given_prerequisite) if incorrect_given_prerequisite else 0.0
    gap = p_correct - p_incorrect
    settings = get_settings()
    # Expert-defined edges start at 1.0; refinement lowers confidence when data
    # does not support the edge and raises it when the configurable gap is met.
    if correct_given_prerequisite or incorrect_given_prerequisite:
        normalized = max(0.0, min(1.0, 0.5 + gap / 2))
        if gap >= settings.edge_confidence_gap_threshold:
            normalized = min(1.0, 0.5 + gap)
        edge.confidence_score = normalized
    return EdgeConfidenceResult(edge.id, edge.prerequisite_id, edge.topic_id, edge.confidence_score, gap, len(correct_given_prerequisite) + len(incorrect_given_prerequisite))


def refine_all_edges(db: Session) -> list[EdgeConfidenceResult]:
    results = [compute_edge_confidence(db, edge) for edge in db.scalars(select(TopicEdge)).all()]
    db.commit()
    return results


def low_confidence_edges(db: Session, threshold: float | None = None) -> list[dict]:
    threshold = threshold if threshold is not None else get_settings().edge_review_threshold
    topics = {topic.id: topic for topic in db.scalars(select(Topic)).all()}
    results = []
    for edge in db.scalars(select(TopicEdge).where(TopicEdge.confidence_score < threshold)).all():
        result = compute_edge_confidence(db, edge)
        results.append({
            'edge_id': result.edge_id,
            'prerequisite_id': result.prerequisite_id,
            'prerequisite_name': topics[result.prerequisite_id].name,
            'topic_id': result.topic_id,
            'topic_name': topics[result.topic_id].name,
            'confidence_score': result.confidence_score,
            'positive_gap': result.positive_gap,
            'sample_count': result.sample_count,
        })
    return sorted(results, key=lambda item: item['confidence_score'])
