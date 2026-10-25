import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Topic, TopicEdge

def load_graph(db: Session) -> nx.DiGraph:
    graph = nx.DiGraph()
    topics = db.scalars(select(Topic)).all()
    for topic in topics:
        graph.add_node(topic.id)
    for edge in db.scalars(select(TopicEdge)).all():
        graph.add_edge(edge.prerequisite_id, edge.topic_id, confidence_score=edge.confidence_score)
    return graph
