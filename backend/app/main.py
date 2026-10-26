from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
import networkx as nx
from app.auth.service import create_access_token, decode_access_token, get_user_by_email, hash_password, verify_password
from app.config import get_settings
from app.db.models import MasteryEstimate, Module, Question, QuizResponse, RoadmapCache, Topic, TopicEdge, Track, User
from app.db.session import Base, SessionLocal, engine, get_db
from app.content import import_library, upgrade_content_schema
from app.content_library import build_library
from app.kst.seed_data import connect_legacy_topics, seed
from app.kst.service import load_graph
from app.mastery.dkt import DKTStrategy
from app.mastery.bkt import BKTParameters, default_parameters, update_mastery
from app.mastery.strategy import StrategySelector
from app.refinement.edge_confidence import low_confidence_edges, refine_all_edges
from app.roadmap.astar import TopicState, generate_roadmap, objective_breakdown
from app.roadmap.pareto import generate_pareto_paths
from app.schemas import AuthRequest, AuthResponse, EdgeCreate, LabBKTRequest, LabDemoStepRequest, LabSearchRequest, ResponseCreate, TopicCreate

def initialize_database() -> None:
    upgrade_content_schema(engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
        import_library(db, build_library())
        connect_legacy_topics(db)

initialize_database()

app = FastAPI(title='ORBIT API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origin_set(), allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
strategy = StrategySelector(DKTStrategy(get_settings().dkt_checkpoint_path))

@app.exception_handler(HTTPException)
async def contract_http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) and 'error' in exc.detail else {'error': {'code': 'http_error', 'message': str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=detail)

@app.on_event('startup')
def startup():
    initialize_database()

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'orbit-backend', 'phase6': True}

def error(code: str, message: str, status_code: int):
    raise HTTPException(status_code=status_code, detail={'error': {'code': code, 'message': message}})

def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith('bearer '):
        error('unauthorized', 'Bearer token required', 401)
    user_id = decode_access_token(authorization.split(' ', 1)[1])
    user = db.get(User, user_id) if user_id else None
    if not user:
        error('unauthorized', 'Invalid or expired token', 401)
    return user

def admin_user(user: User = Depends(current_user)) -> User:
    if user.email.lower() not in get_settings().admin_email_set():
        error('forbidden', 'Admin access required', 403)
    return user

def serialize_topic(topic: Topic):
    return {'id': topic.id, 'slug': topic.slug, 'name': topic.name, 'description': topic.description, 'estimated_minutes': topic.estimated_minutes, 'content_url': topic.content_url, 'module_id': topic.module_id, 'objectives': topic.learning_objectives or [], 'difficulty': topic.difficulty_level, 'review_status': topic.review_status}

def serialize_edge(edge: TopicEdge):
    return {'id': edge.id, 'prerequisite_id': edge.prerequisite_id, 'topic_id': edge.topic_id, 'confidence_score': edge.confidence_score}

@app.post('/api/v1/auth/signup', response_model=AuthResponse, status_code=201)
def signup(payload: AuthRequest, db: Session = Depends(get_db)):
    if get_user_by_email(db, payload.email): error('email_exists', 'Email is already registered', 400)
    user = User(email=payload.email.lower().strip(), password_hash=hash_password(payload.password)); db.add(user); db.commit(); db.refresh(user)
    return {'user_id': user.id, 'token': create_access_token(user.id)}

@app.post('/api/v1/auth/login', response_model=AuthResponse)
def login(payload: AuthRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash): error('invalid_credentials', 'Invalid email or password', 401)
    return {'user_id': user.id, 'token': create_access_token(user.id)}

@app.get('/api/v1/kst')
def get_kst(db: Session = Depends(get_db)):
    return {'topics': [serialize_topic(t) for t in db.scalars(select(Topic)).all()], 'edges': [serialize_edge(e) for e in db.scalars(select(TopicEdge)).all()]}

@app.get('/api/v1/ai-lab/graph')
def ai_lab_graph(user: User = Depends(current_user), db: Session = Depends(get_db)):
    topics = db.scalars(select(Topic).order_by(Topic.name)).all()
    edges = db.scalars(select(TopicEdge)).all()
    modules = {m.id:m for m in db.scalars(select(Module)).all()}
    tracks = {t.id:t for t in db.scalars(select(Track)).all()}
    rows = {r.topic_id:r for r in db.scalars(select(MasteryEstimate).where(MasteryEstimate.student_id == user.id)).all()}
    dkt_active = strategy._has_enough_interactions(db, user.id)
    by_id = {t.id:t for t in topics}
    prereqs: dict[str,list[str]] = {t.id:[] for t in topics}
    dependents: dict[str,list[str]] = {t.id:[] for t in topics}
    missing_edges = []
    for edge in edges:
        if edge.prerequisite_id not in by_id or edge.topic_id not in by_id:
            missing_edges.append({'prerequisite_id':edge.prerequisite_id,'topic_id':edge.topic_id})
            continue
        prereqs[edge.topic_id].append(edge.prerequisite_id)
        dependents[edge.prerequisite_id].append(edge.topic_id)
    mastery = {}
    for topic in topics:
        row = rows.get(topic.id)
        # Do not present the configured BKT prior as observed learner mastery.
        value = row.p_mastery if row else (strategy.estimate(db, user.id, topic.id) if dkt_active else None)
        mastery[topic.id] = value
    nodes = []
    for topic in topics:
        value = mastery[topic.id]
        if value is None: mastery_status = 'unknown'
        elif value >= .85: mastery_status = 'mastered'
        elif value >= .45: mastery_status = 'partial'
        else: mastery_status = 'unmastered'
        required = prereqs[topic.id]
        if not required: availability = 'available'
        elif any(mastery[item] is not None and mastery[item] < .85 for item in required): availability = 'blocked'
        elif all(mastery[item] is not None and mastery[item] >= .85 for item in required): availability = 'available'
        else: availability = 'unknown'
        module = modules.get(topic.module_id)
        track = tracks.get(module.track_id) if module else None
        nodes.append({'id':topic.id,'slug':topic.slug,'name':topic.name,'description':topic.description,'module_id':topic.module_id,'module_name':module.title if module else None,'track_id':track.id if track else None,'track_name':track.title if track else None,'difficulty':topic.difficulty_level,'estimated_minutes':topic.estimated_minutes,'mastery_probability':value,'mastery_observed':topic.id in rows,'mastery_source':rows[topic.id].source if topic.id in rows else ('dkt' if dkt_active else None),'mastery_status':mastery_status,'availability':availability,'prerequisite_ids':prereqs[topic.id],'dependent_ids':dependents[topic.id]})
    graph = load_graph(db)
    params = default_parameters()
    return {'nodes':nodes,'edges':[serialize_edge(e) for e in edges],'bkt_parameters':{'p_init':params.p_init,'p_transit':params.p_transit,'p_slip':params.p_slip,'p_guess':params.p_guess},'diagnostics':{'missing_edge_nodes':missing_edges,'is_dag':nx.is_directed_acyclic_graph(graph),'formal_knowledge_space_claim':False,'note':'This is the stored prerequisite graph, not a claim of a formally complete knowledge-space model.'}}

def _bkt_trace(prior: float, correct: bool, params: BKTParameters):
    if correct:
        p_response_known = 1 - params.p_slip
        p_response_unknown = params.p_guess
    else:
        p_response_known = params.p_slip
        p_response_unknown = 1 - params.p_guess
    known_joint = prior * p_response_known
    unknown_joint = (1 - prior) * p_response_unknown
    denominator = known_joint + unknown_joint
    posterior = known_joint / denominator if denominator else 0.0
    final = update_mastery(prior, correct, params)
    return {'prior_mastery':prior,'observed_response':'correct' if correct else 'incorrect','probability_response_if_known':p_response_known,'probability_response_if_unknown':p_response_unknown,'weighted_known_likelihood':known_joint,'weighted_unknown_likelihood':unknown_joint,'observation_posterior':posterior,'learning_transition':params.p_transit,'final_mastery':final,'interpretation':'Observation update estimates knowledge given this response; the subsequent P(T) transition models learning after the opportunity.'}

def _configured_bkt(params: LabBKTRequest | None = None):
    actual = default_parameters()
    if params is None: return actual
    return BKTParameters(actual.p_init, params.p_transit if params.p_transit is not None else actual.p_transit, params.p_slip if params.p_slip is not None else actual.p_slip, params.p_guess if params.p_guess is not None else actual.p_guess)

@app.post('/api/v1/ai-lab/bkt/step')
def ai_lab_bkt_step(payload: LabBKTRequest, user: User = Depends(current_user)):
    params = _configured_bkt(payload)
    return {'mode':'stateless_simulation','persisted':False,'parameters':{'p_init':params.p_init,'p_transit':params.p_transit,'p_slip':params.p_slip,'p_guess':params.p_guess},'trace':_bkt_trace(payload.prior_mastery,payload.correct,params)}

@app.post('/api/v1/ai-lab/search')
def ai_lab_search(payload: LabSearchRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    graph, topics, rows, mastery, states = _roadmap_context(user, db)
    if payload.target_topic_id not in topics: error('not_found','Target topic not found in the prerequisite graph',404)
    if payload.start_topic_id and payload.start_topic_id not in topics: error('not_found','Start topic not found in the prerequisite graph',404)
    events: list[dict] = []
    path = generate_roadmap(graph, mastery, states, payload.target_topic_id, payload.start_topic_id, events)
    search_path = next((e.get('search_path') for e in events if e.get('target_reached')), None)
    max_minutes = max((topic.estimated_minutes for topic in topics.values()), default=60)
    return {'mode':'authenticated_learner','target_topic_id':payload.target_topic_id,'start_topic_id':payload.start_topic_id,'final_roadmap_path':path,'search_path':search_path,'trace':events,'mastery':mastery,'cost_weights':{'mastery':get_settings().w1,'retention':get_settings().w2,'time':get_settings().w3},'heuristic':'ORBIT remaining mastery-deficit heuristic from astar.py (sum of deficits in the target ancestry not already in the current node ancestry)','max_minutes_normalizer':max_minutes,'persisted':False}

@app.post('/api/v1/ai-lab/demo/step')
def ai_lab_demo_step(payload: LabDemoStepRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    graph, topics, _, _, _ = _roadmap_context(user, db)
    if payload.topic_id not in topics or payload.target_topic_id not in topics: error('not_found','Demo topic or target not found in the prerequisite graph',404)
    if payload.start_topic_id and payload.start_topic_id not in topics: error('not_found','Demo start topic not found in the prerequisite graph',404)
    unknown_ids = set(payload.mastery) - set(topics)
    if unknown_ids: error('invalid_demo_state','Synthetic mastery contains topics outside the graph',400)
    assessment = None
    correct = payload.correct
    if payload.question_id:
        question = db.get(Question,payload.question_id)
        if not question or question.review_status != 'approved': error('question_unavailable','Published demo question not found',404)
        if question.topic_id != payload.topic_id: error('question_topic_mismatch','Demo question does not belong to the selected topic',400)
        if payload.selected_choice_index is None or payload.selected_choice_index >= len(question.choices): error('invalid_choice','Selected choice is out of range',400)
        correct = payload.selected_choice_index == question.correct_choice_index
        assessment = {'question_id':question.id,'prompt':question.prompt,'selected_choice_index':payload.selected_choice_index,'correct_choice_index':question.correct_choice_index,'correct':correct,'explanation':question.explanation}
    if correct is None: error('invalid_demo_answer','A correct/incorrect result is required',400)
    params = default_parameters()
    synthetic_mastery = {topic_id:payload.mastery.get(topic_id,params.p_init) for topic_id in topics}
    prior = synthetic_mastery[payload.topic_id]
    bkt = _bkt_trace(prior,correct,params)
    synthetic_mastery[payload.topic_id] = bkt['final_mastery']
    now = datetime.now(timezone.utc)
    states_before = {topic_id:TopicState(mastery=payload.mastery.get(topic_id,params.p_init),last_updated=None,estimated_minutes=topics[topic_id].estimated_minutes) for topic_id in topics}
    states_after = {topic_id:TopicState(mastery=synthetic_mastery[topic_id],last_updated=now if topic_id == payload.topic_id else None,estimated_minutes=topics[topic_id].estimated_minutes) for topic_id in topics}
    path_before = generate_roadmap(graph,{topic_id:state.mastery for topic_id,state in states_before.items()},states_before,payload.target_topic_id,payload.start_topic_id)
    events: list[dict] = []
    path_after = generate_roadmap(graph,synthetic_mastery,states_after,payload.target_topic_id,payload.start_topic_id,events)
    search_path = next((e.get('search_path') for e in events if e.get('target_reached')), None)
    return {'mode':'synthetic_integrated_demo','persisted':False,'parameters':{'p_init':params.p_init,'p_transit':params.p_transit,'p_slip':params.p_slip,'p_guess':params.p_guess},'topic_id':payload.topic_id,'assessment':assessment,'bkt':bkt,'synthetic_mastery':synthetic_mastery,'path_before':path_before,'path_after':path_after,'path_changed':path_before != path_after,'target_topic_id':payload.target_topic_id,'start_topic_id':payload.start_topic_id,'search_path':search_path,'a_star_trace':events,'explanation':'This deterministic scenario uses ORBIT’s configured BKT formula and the instrumented production roadmap function. It is synthetic and was not written to learner history.'}

@app.get('/api/v1/content/library')
def content_library(db: Session = Depends(get_db)):
    tracks = db.scalars(select(Track).where(Track.status == 'published').order_by(Track.sort_order, Track.title)).all()
    modules = db.scalars(select(Module).order_by(Module.sort_order, Module.title)).all()
    topics = db.scalars(select(Topic).where(Topic.review_status == 'approved').order_by(Topic.name)).all()
    questions = db.scalars(select(Question).where(Question.review_status == 'approved')).all()
    q_counts: dict[str, int] = {}
    for q in questions: q_counts[q.topic_id] = q_counts.get(q.topic_id, 0) + 1
    return {'tracks':[{'id':t.id,'title':t.title,'description':t.description,'modules':[{'id':m.id,'title':m.title,'description':m.description,'topics':[serialize_topic(topic) | {'question_count':q_counts.get(topic.id,0)} for topic in topics if topic.module_id == m.id]} for m in modules if m.track_id == t.id]} for t in tracks]}

@app.get('/api/v1/content/topics/{topic_id}')
def content_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id) or db.scalar(select(Topic).where(Topic.slug == topic_id))
    if not topic or topic.review_status != 'approved': error('not_found', 'Published topic not found', 404)
    edges = db.scalars(select(TopicEdge).where(TopicEdge.topic_id == topic.id)).all()
    prerequisite_ids = [edge.prerequisite_id for edge in edges]
    prerequisites = [serialize_topic(t) for t in db.scalars(select(Topic).where(Topic.id.in_(prerequisite_ids))).all()] if prerequisite_ids else []
    question_count = len(db.scalars(select(Question).where(Question.topic_id == topic.id, Question.review_status == 'approved')).all())
    return serialize_topic(topic) | {'content':topic.learning_content or {}, 'prerequisites':prerequisites, 'question_count':question_count}

@app.post('/api/v1/kst/topics', status_code=201)
def create_topic(payload: TopicCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    topic = Topic(**payload.model_dump()); db.add(topic); db.commit(); db.refresh(topic); return serialize_topic(topic)

@app.post('/api/v1/kst/edges', status_code=201)
def create_edge(payload: EdgeCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    if not db.get(Topic, payload.prerequisite_id) or not db.get(Topic, payload.topic_id): error('not_found', 'Both topics must exist', 404)
    edge = TopicEdge(**payload.model_dump()); db.add(edge); db.commit(); db.refresh(edge); return serialize_edge(edge)

@app.post('/api/v1/kst/edges/refine')
def refine_edges(user: User = Depends(admin_user), db: Session = Depends(get_db)):
    results = refine_all_edges(db)
    return {'updated_edges': len(results), 'edges': [result.__dict__ for result in results]}

@app.get('/api/v1/admin/edges/low-confidence')
def review_edges(threshold: float | None = Query(default=None, ge=0, le=1), user: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {'threshold': threshold if threshold is not None else get_settings().edge_review_threshold, 'edges': low_confidence_edges(db, threshold)}

def question_payload(q: Question):
    return {'id': q.id, 'topic_id': q.topic_id, 'prompt': q.prompt, 'choices': q.choices, 'question_type':q.question_type, 'difficulty':q.difficulty, 'learning_objective':q.learning_objective}

@app.get('/api/v1/quiz/diagnostic')
def diagnostic(track_id: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if track_id is not None:
        track = db.get(Track, track_id)
        if track is None:
            error('not_found', 'Track not found', 404)
        topics = db.scalars(
            select(Topic)
            .join(Module, Topic.module_id == Module.id)
            .where(Module.track_id == track_id)
            .order_by(Module.sort_order, Topic.name, Topic.id)
        ).all()
    else:
        incoming_topic_ids = set(db.scalars(select(TopicEdge.topic_id)).all())
        topics = [
            topic
            for topic in db.scalars(select(Topic).order_by(Topic.name, Topic.id)).all()
            if topic.id not in incoming_topic_ids
        ][:12]
    questions = []
    for topic in topics:
        q = db.scalars(
            select(Question)
            .where(Question.topic_id == topic.id, Question.review_status == 'approved')
            .order_by(Question.id)
            .limit(1)
        ).first()
        if q: questions.append(question_payload(q))
    return {'questions': questions}

@app.get('/api/v1/quiz/topic/{topic_id}')
def topic_quiz(topic_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.get(Topic, topic_id): error('not_found', 'Topic not found', 404)
    questions = db.scalars(select(Question).where(Question.topic_id == topic_id, Question.review_status == 'approved').order_by(Question.difficulty)).all()
    return {'questions': [question_payload(q) for q in questions]}

@app.post('/api/v1/quiz/response')
def submit_response(payload: ResponseCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.get(Question, payload.question_id)
    if not q: error('not_found', 'Question not found', 404)
    if q.review_status != 'approved': error('question_unavailable', 'This question is not approved for scored practice', 409)
    if not 0 <= payload.selected_choice_index < len(q.choices): error('invalid_choice', 'Selected choice is out of range', 400)
    correct = payload.selected_choice_index == q.correct_choice_index
    db.add(QuizResponse(student_id=user.id, question_id=q.id, topic_id=q.topic_id, correct=correct)); db.flush()
    updated, source = strategy.update(db, user.id, q.topic_id, correct)
    db.execute(delete(RoadmapCache).where(RoadmapCache.student_id == user.id)); db.commit()
    return {'correct': correct, 'correct_choice_index': q.correct_choice_index, 'explanation':q.explanation, 'distractor_explanations':q.distractor_explanations or [], 'updated_mastery': {'topic_id': q.topic_id, 'p_mastery': updated, 'source': source}}

@app.get('/api/v1/mastery/me')
def mastery_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    topics = db.scalars(select(Topic)).all(); rows = {row.topic_id: row for row in db.scalars(select(MasteryEstimate).where(MasteryEstimate.student_id == user.id)).all()}; now = datetime.now(timezone.utc)
    estimates = []
    dkt_active = strategy._has_enough_interactions(db, user.id)
    for topic in topics:
        row = rows.get(topic.id)
        value = strategy.estimate(db, user.id, topic.id) if dkt_active else (row.p_mastery if row else get_settings().p_init)
        source = 'dkt' if dkt_active else (row.source if row else 'bkt')
        estimates.append({'topic_id': topic.id, 'topic_name': topic.name, 'p_mastery': value, 'last_updated': (row.last_updated if row else now).isoformat(), 'source': source})
    return {'estimates': estimates}

def _roadmap_context(user: User, db: Session):
    graph = load_graph(db); topics = {topic.id: topic for topic in db.scalars(select(Topic)).all()}; rows = {row.topic_id: row for row in db.scalars(select(MasteryEstimate).where(MasteryEstimate.student_id == user.id)).all()}
    mastery = {topic_id: (rows[topic_id].p_mastery if topic_id in rows else strategy.estimate(db, user.id, topic_id)) for topic_id in topics}
    states = {topic_id: TopicState(mastery=mastery[topic_id], last_updated=rows[topic_id].last_updated if topic_id in rows else None, estimated_minutes=topics[topic_id].estimated_minutes) for topic_id in topics}
    return graph, topics, rows, mastery, states

def _node_payload(tid: str, order: int, topics: dict, graph: nx.DiGraph, mastery: dict, states: dict, max_minutes: int):
    breakdown = objective_breakdown(states[tid], max_minutes); prereqs = [topics[p].name for p in graph.predecessors(tid) if p in topics]
    reason = f"Low mastery ({mastery[tid]:.0%})"
    if prereqs: reason += f"; prerequisite for {topics[tid].name if order == 1 else 'the next step'}"
    reason += '; not yet studied.' if states[tid].last_updated is None else '.'
    return {'topic_id': tid, 'topic_name': topics[tid].name, 'order': order, 'mastery_estimate': mastery[tid], 'objective_breakdown': breakdown, 'reason': reason}

def build_weighted_roadmap(user: User, db: Session, target_topic_id: str | None):
    graph, topics, rows, mastery, states = _roadmap_context(user, db); path_ids = generate_roadmap(graph, mastery, states, target_topic_id); max_minutes = max((topic.estimated_minutes for topic in topics.values()), default=60)
    return {'mode': 'weighted', 'path': [_node_payload(tid, i, topics, graph, mastery, states, max_minutes) for i, tid in enumerate(path_ids, 1)], 'computed_at': datetime.now(timezone.utc).isoformat()}

def build_pareto_roadmap(user: User, db: Session, target_topic_id: str | None):
    graph, topics, rows, mastery, states = _roadmap_context(user, db); candidates = generate_pareto_paths(graph, mastery, states, target_topic_id); max_minutes = max((topic.estimated_minutes for topic in topics.values()), default=60); paths = []
    for label, node_ids, score in candidates:
        path = [_node_payload(tid, i, topics, graph, mastery, states, max_minutes) for i, tid in enumerate(node_ids, 1)]
        paths.append({'label': label, 'path': path, 'objective_totals': {'mastery_deficit': score.mastery, 'retention_penalty': score.retention, 'time_cost': score.time}})
    return {'mode': 'pareto', 'paths': paths, 'computed_at': datetime.now(timezone.utc).isoformat()}

def resolve_roadmap_target(db: Session, user: User, track_id: str | None, target_topic_id: str | None) -> str:
    track = db.get(Track, track_id) if track_id is not None else None
    if track_id is not None and track is None:
        error('not_found', 'Track not found', 404)
    if target_topic_id is not None:
        if db.get(Topic, target_topic_id) is None:
            error('not_found', 'Topic not found', 404)
        return target_topic_id
    if track is None:
        track = db.scalar(select(Track).order_by(Track.sort_order, Track.id).limit(1))
    if track is None:
        error('not_found', 'No published learning tracks are available', 404)

    graph, topics, _, mastery, _ = _roadmap_context(user, db)
    modules = {module.id: module for module in db.scalars(select(Module)).all()}
    track_topics = {
        topic_id: topic
        for topic_id, topic in topics.items()
        if topic.module_id is not None
        and topic.module_id in modules
        and modules[topic.module_id].track_id == track.id
    }
    if not track_topics:
        error('track_empty', 'Track has no topics', 404)

    terminal_topics = [
        topic_id
        for topic_id in track_topics
        if not any(successor in track_topics for successor in graph.successors(topic_id))
    ]
    candidates = terminal_topics or list(track_topics)
    return min(
        candidates,
        key=lambda topic_id: (
            mastery[topic_id],
            -modules[track_topics[topic_id].module_id].sort_order,
            (track_topics[topic_id].slug or track_topics[topic_id].name).casefold(),
            topic_id,
        ),
    )

@app.get('/api/v1/roadmap/me')
def roadmap_me(target_topic_id: str | None = Query(default=None), track_id: str | None = Query(default=None), mode: str = Query(default='weighted'), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if mode not in {'weighted', 'pareto'}: error('invalid_mode', 'mode must be weighted or pareto', 400)
    target_topic_id = resolve_roadmap_target(db, user, track_id, target_topic_id)
    cached = db.scalar(select(RoadmapCache).where(RoadmapCache.student_id == user.id, RoadmapCache.target_topic_id == target_topic_id, RoadmapCache.mode == mode))
    if cached: return cached.roadmap_json
    result = build_weighted_roadmap(user, db, target_topic_id) if mode == 'weighted' else build_pareto_roadmap(user, db, target_topic_id)
    db.add(RoadmapCache(student_id=user.id, target_topic_id=target_topic_id, mode=mode, roadmap_json=result)); db.commit()
    return result
