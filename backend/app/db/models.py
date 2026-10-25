from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def uuid_str() -> str:
    return str(uuid4())

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Track(Base):
    __tablename__ = 'tracks'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default='')
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default='published')

class Module(Base):
    __tablename__ = 'modules'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    track_id: Mapped[str] = mapped_column(ForeignKey('tracks.id'), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default='')
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class Topic(Base):
    __tablename__ = 'topics'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    content_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    slug: Mapped[str | None] = mapped_column(String(180), nullable=True, unique=True, index=True)
    module_id: Mapped[str | None] = mapped_column(ForeignKey('modules.id'), nullable=True, index=True)
    learning_objectives: Mapped[list] = mapped_column(JSON, default=list)
    learning_content: Mapped[dict] = mapped_column(JSON, default=dict)
    difficulty_level: Mapped[str] = mapped_column(String(20), default='beginner')
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    provenance: Mapped[str] = mapped_column(String(200), default='ORBIT original content')
    review_status: Mapped[str] = mapped_column(String(20), default='approved')

class TopicEdge(Base):
    __tablename__ = 'topic_edges'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    prerequisite_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    __table_args__ = (UniqueConstraint('prerequisite_id', 'topic_id', name='uq_topic_edge'),)

class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    choices: Mapped[list] = mapped_column(JSON)
    correct_choice_index: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[float] = mapped_column(Float)
    question_type: Mapped[str] = mapped_column(String(40), default='multiple_choice')
    explanation: Mapped[str] = mapped_column(Text, default='')
    distractor_explanations: Mapped[list] = mapped_column(JSON, default=list)
    learning_objective: Mapped[str] = mapped_column(String(240), default='')
    scoring_criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    provenance: Mapped[str] = mapped_column(String(200), default='ORBIT original content')
    review_status: Mapped[str] = mapped_column(String(20), default='approved')

class QuizResponse(Base):
    __tablename__ = 'quiz_responses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'), index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), index=True)
    correct: Mapped[bool] = mapped_column(Boolean)
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class MasteryEstimate(Base):
    __tablename__ = 'mastery_estimates'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), index=True)
    p_mastery: Mapped[float] = mapped_column(Float)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(20), default='bkt')
    __table_args__ = (UniqueConstraint('student_id', 'topic_id', name='uq_mastery_student_topic'),)

class RoadmapCache(Base):
    __tablename__ = 'roadmap_cache'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    target_topic_id: Mapped[str | None] = mapped_column(ForeignKey('topics.id'), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default='weighted')
    roadmap_json: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('student_id', 'target_topic_id', 'mode', name='uq_roadmap_cache_key'),)
