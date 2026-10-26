from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Topic, TopicEdge, Question, User, MasteryEstimate
from app.auth.service import hash_password

TOPICS = [
    ('Python Syntax', 'Variables, expressions, control flow, and core Python syntax.', 30),
    ('Functions', 'Defining, calling, and composing reusable Python functions.', 35),
    ('Recursion', 'Solving problems by reducing them to smaller self-similar instances.', 45),
    ('Trees', 'Hierarchical data structures and tree traversals.', 50),
    ('Graphs', 'Graph representations, traversal, and shortest paths.', 55),
    ('Machine Learning', 'Introductory supervised learning concepts and workflows.', 60),
]
QUESTIONS = {
    'Python Syntax': [
        ('Which keyword starts a conditional branch in Python?', ['if', 'when', 'case', 'branch'], 0, 0.1),
        ('What type is returned by len([1, 2, 3])?', ['str', 'int', 'float', 'bool'], 1, 0.1),
        ('Which symbol begins a comment in Python?', ['//', '#', '--', '/*'], 1, 0.2),
        ('What does range(3) produce?', ['0, 1, 2', '1, 2, 3', '0, 1, 2, 3', '3'], 0, 0.4),
        ('Which collection is immutable?', ['list', 'dict', 'set', 'tuple'], 3, 0.7),
    ],
    'Functions': [
        ('Which keyword defines a function?', ['func', 'def', 'function', 'lambda'], 1, 0.1),
        ('What does return do?', ['Prints output', 'Ends a function with a value', 'Loops', 'Imports code'], 1, 0.2),
        ('A parameter is best described as:', ['A function input name', 'A module', 'A loop', 'A class'], 0, 0.3),
        ('What is a *args parameter used for?', ['Keyword-only inputs', 'Variable positional inputs', 'Errors', 'Type hints'], 1, 0.6),
        ('A lambda creates:', ['An anonymous function', 'A list', 'A package', 'A generator only'], 0, 0.7),
    ],
    'Recursion': [
        ('Every recursive function needs a:', ['Global variable', 'Base case', 'Class', 'Decorator'], 1, 0.2),
        ('Recursion solves a problem by:', ['Repeating the same exact call forever', 'Calling a smaller version of itself', 'Sorting inputs', 'Using SQL'], 1, 0.2),
        ('What is a risk of missing a base case?', ['Syntax highlighting', 'Infinite recursion', 'Faster code', 'Type coercion'], 1, 0.3),
        ('The call stack stores:', ['Pending function frames', 'Only constants', 'Database tables', 'CSS rules'], 0, 0.5),
        ('Merge sort typically has recursion depth of:', ['O(1)', 'O(log n)', 'O(n^2)', 'O(2^n)'], 1, 0.7),
    ],
    'Trees': [
        ('A tree is a graph with:', ['Cycles everywhere', 'No cycles and a hierarchy', 'Only one node', 'No edges'], 1, 0.2),
        ('A root node has:', ['No parent', 'Two parents', 'Only children and no value', 'A cycle'], 0, 0.2),
        ('In-order traversal of a BST yields:', ['Reverse order always', 'Sorted order', 'Random order', 'Level order'], 1, 0.4),
        ('A leaf node has:', ['No children', 'No parent', 'Two roots', 'A cycle'], 0, 0.3),
        ('Breadth-first tree traversal uses a:', ['Queue', 'Stack only', 'Set only', 'Heap sort'], 0, 0.6),
    ],
    'Graphs': [
        ('A graph edge connects:', ['Two vertices', 'Two files', 'Two functions only', 'Two arrays only'], 0, 0.1),
        ('BFS is useful for unweighted shortest paths because it explores by:', ['Depth cost', 'Distance layers', 'Random priority', 'Node name'], 1, 0.4),
        ('DFS commonly uses:', ['A stack or recursion', 'A database', 'A CSS grid', 'A compiler flag'], 0, 0.3),
        ('A DAG contains:', ['Directed cycles', 'No directed cycles', 'Only undirected edges', 'No vertices'], 1, 0.5),
        ('Dijkstra assumes edge weights are:', ['Non-negative', 'Always negative', 'Strings', 'Boolean only'], 0, 0.7),
    ],
    'Machine Learning': [
        ('A feature is:', ['An input variable', 'Only a label', 'A database index', 'A loop keyword'], 0, 0.2),
        ('Supervised learning uses:', ['Labeled examples', 'No data', 'Only graphs', 'Only rules'], 0, 0.2),
        ('Overfitting means a model:', ['Generalizes perfectly', 'Memorizes training noise', 'Has no parameters', 'Cannot train'], 1, 0.4),
        ('A validation set helps with:', ['Model selection', 'Writing comments', 'Sorting lists', 'Hashing passwords'], 0, 0.6),
        ('Classification predicts:', ['Discrete labels', 'Only continuous numbers', 'Graph edges only', 'SQL rows'], 0, 0.5),
    ],
}

def seed(db: Session):
    existing = db.scalar(select(Topic).limit(1))
    if existing:
        return
    by_name = {}
    for name, description, minutes in TOPICS:
        topic = Topic(name=name, description=description, estimated_minutes=minutes, content_url='https://docs.python.org/3/tutorial/')
        db.add(topic); db.flush(); by_name[name] = topic
    edges = [('Python Syntax', 'Functions'), ('Functions', 'Recursion'), ('Recursion', 'Trees'), ('Trees', 'Graphs'), ('Graphs', 'Machine Learning'), ('Functions', 'Machine Learning')]
    for a, b in edges:
        db.add(TopicEdge(prerequisite_id=by_name[a].id, topic_id=by_name[b].id, confidence_score=1.0))
    for topic_name, items in QUESTIONS.items():
        for prompt, choices, correct, difficulty in items:
            db.add(Question(topic_id=by_name[topic_name].id, prompt=prompt, choices=choices, correct_choice_index=correct, difficulty=difficulty))
    demo = User(email='demo@orbit.dev', password_hash=hash_password('orbit-demo'))
    db.add(demo); db.flush()
    for name, value in [('Python Syntax', .88), ('Functions', .68), ('Recursion', .35), ('Trees', .25)]:
        db.add(MasteryEstimate(student_id=demo.id, topic_id=by_name[name].id, p_mastery=value, source='bkt'))
    db.commit()


def connect_legacy_topics(db: Session):
    """Keep historical seed topics visible in their closest track and connected to the library."""
    module_by_name = {
        'Python Syntax': 'py-core',
        'Functions': 'py-core',
        'Recursion': 'py-core',
        'Trees': 'computer-science',
        'Graphs': 'computer-science',
        'Machine Learning': 'computer-science',
    }
    legacy = {
        topic.name: topic
        for topic in db.scalars(select(Topic).where(Topic.name.in_(module_by_name))).all()
    }
    for name, module_id in module_by_name.items():
        topic = legacy.get(name)
        if topic is not None:
            topic.module_id = module_id
            topic.provenance = 'ORBIT legacy seed; retained to preserve learner history'

    prerequisite = db.scalar(select(Topic).where(Topic.slug == 'cs-graphs-overview'))
    graph_topic = legacy.get('Graphs')
    if prerequisite is not None and graph_topic is not None:
        # The library graph overview is a foundation for the retained legacy graph-traversal topic.
        edge = db.scalar(
            select(TopicEdge).where(
                TopicEdge.prerequisite_id == prerequisite.id,
                TopicEdge.topic_id == graph_topic.id,
            )
        )
        if edge is None:
            db.add(TopicEdge(
                prerequisite_id=prerequisite.id,
                topic_id=graph_topic.id,
                confidence_score=1.0,
            ))
    db.commit()
