"""Duplicate-safe content import and validation for the ORBIT learning library."""
from __future__ import annotations
from collections import Counter
import re
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
import networkx as nx
from app.db.models import Module, Question, Topic, TopicEdge, Track

# Additive compatibility migration for databases created before structured content existed.
_ADDITIONS = {
    'topics': {'slug': 'VARCHAR(180)', 'module_id': 'VARCHAR(100)', 'learning_objectives': 'JSON', 'learning_content': 'JSON', 'difficulty_level': "VARCHAR(20) DEFAULT 'beginner'", 'content_version': 'INTEGER DEFAULT 1', 'provenance': "VARCHAR(200) DEFAULT 'legacy'", 'review_status': "VARCHAR(20) DEFAULT 'approved'"},
    'questions': {'question_type': "VARCHAR(40) DEFAULT 'multiple_choice'", 'explanation': "TEXT DEFAULT ''", 'distractor_explanations': 'JSON', 'learning_objective': "VARCHAR(240) DEFAULT ''", 'scoring_criteria': 'JSON', 'content_version': 'INTEGER DEFAULT 1', 'provenance': "VARCHAR(200) DEFAULT 'legacy'", 'review_status': "VARCHAR(20) DEFAULT 'approved'"},
}

def upgrade_content_schema(engine) -> None:
    """Upgrade old installations without dropping or rewriting learner data."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDITIONS.items():
            if table not in inspector.get_table_names():
                continue
            existing = {column['name'] for column in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}')

def validate_library(data: dict) -> list[str]:
    errors: list[str] = []
    tracks = data.get('tracks', [])
    track_ids = {t.get('id') for t in tracks}
    modules = data.get('modules', [])
    module_ids = {m.get('id') for m in modules}
    for module in modules:
        if module.get('track_id') not in track_ids:
            errors.append(f"module {module.get('id')} references missing track")
    topics = data.get('topics', [])
    slugs = [t.get('slug') for t in topics]
    duplicates = [slug for slug, count in Counter(slugs).items() if count > 1]
    errors.extend(f'duplicate topic slug: {slug}' for slug in duplicates)
    topic_slugs = set(slugs)
    graph = nx.DiGraph()
    for topic in topics:
        slug = topic.get('slug', '<missing>')
        if not slug or not topic.get('title') or not topic.get('summary'):
            errors.append(f'{slug}: slug/title/summary required')
        if topic.get('module_id') not in module_ids:
            errors.append(f'{slug}: missing module reference')
        for field in ('objectives', 'explanation', 'terminology', 'worked_examples', 'exercises', 'misconceptions', 'mastery_criteria'):
            if not topic.get(field): errors.append(f'{slug}: missing {field}')
        graph.add_node(slug)
        for prereq in topic.get('prerequisites', []):
            if prereq not in topic_slugs: errors.append(f'{slug}: missing prerequisite {prereq}')
            graph.add_edge(prereq, slug)
        questions = topic.get('questions', [])
        if not 8 <= len(questions) <= 12:
            errors.append(f'{slug}: expected 8-12 questions, got {len(questions)}')
        prompts = [q.get('prompt', '').strip().casefold() for q in questions]
        if len(prompts) != len(set(prompts)): errors.append(f'{slug}: duplicate question prompt')
        prompt_tokens = [set(re.findall(r'[a-z0-9]+', prompt)) for prompt in prompts]
        for left in range(len(prompt_tokens)):
            for right in range(left + 1, len(prompt_tokens)):
                union = prompt_tokens[left] | prompt_tokens[right]
                overlap = len(prompt_tokens[left] & prompt_tokens[right]) / max(1, len(union))
                if overlap >= 0.90:
                    errors.append(f'{slug}: near-duplicate question prompts {left + 1} and {right + 1}')
        for i, q in enumerate(questions):
            choices = q.get('choices', [])
            if not q.get('prompt') or len(choices) < 2 or not 0 <= q.get('correct', -1) < len(choices):
                errors.append(f'{slug}: question {i + 1} has invalid format or answer key')
            if not q.get('explanation') or not q.get('learning_objective'):
                errors.append(f'{slug}: question {i + 1} needs explanation and objective mapping')
    if not nx.is_directed_acyclic_graph(graph): errors.append('prerequisite graph contains a cycle')
    return errors

def import_library(db: Session, data: dict) -> dict:
    """Validate first; atomically upsert stable slugs and content, never reset users."""
    errors = validate_library(data)
    if errors: raise ValueError('Content validation failed:\n' + '\n'.join(errors))
    for row in data['tracks']:
        obj = db.get(Track, row['id'])
        if obj is None: obj = Track(id=row['id']); db.add(obj)
        for field in ('title', 'description', 'sort_order', 'status'): setattr(obj, field, row.get(field, getattr(obj, field, None)))
    db.flush()
    for row in data['modules']:
        obj = db.get(Module, row['id'])
        if obj is None: obj = Module(id=row['id']); db.add(obj)
        for field in ('track_id', 'title', 'description', 'sort_order'): setattr(obj, field, row.get(field, getattr(obj, field, None)))
    db.flush()
    by_slug: dict[str, Topic] = {}
    for row in data['topics']:
        obj = db.scalar(select(Topic).where(Topic.slug == row['slug']))
        if obj is None:
            obj = Topic(id=str(uuid5(NAMESPACE_URL, 'orbit:topic:' + row['slug'])), slug=row['slug'], name=row['title'], description=row['summary'], estimated_minutes=row.get('minutes', 20)); db.add(obj)
        obj.name = row['title']; obj.description = row['summary']; obj.estimated_minutes = row.get('minutes', 20)
        obj.module_id = row['module_id']; obj.slug = row['slug']; obj.difficulty_level = row.get('difficulty', 'beginner')
        obj.learning_objectives = row['objectives']; obj.learning_content = {k: row[k] for k in ('explanation', 'terminology', 'worked_examples', 'exercises', 'misconceptions', 'mastery_criteria')}
        obj.content_version = row.get('version', 1); obj.provenance = row.get('provenance', 'ORBIT original content'); obj.review_status = row.get('review_status', 'approved')
        by_slug[row['slug']] = obj
    db.flush()
    # Upsert edges by stable endpoint pair, preserving empirical confidence when present.
    for row in data['topics']:
        for prereq in row.get('prerequisites', []):
            a, b = by_slug[prereq], by_slug[row['slug']]
            edge = db.scalar(select(TopicEdge).where(TopicEdge.prerequisite_id == a.id, TopicEdge.topic_id == b.id))
            if edge is None: db.add(TopicEdge(prerequisite_id=a.id, topic_id=b.id, confidence_score=1.0))
    db.flush()
    q_count = 0
    for row in data['topics']:
        topic = by_slug[row['slug']]
        for item in row['questions']:
            q = db.scalar(select(Question).where(Question.topic_id == topic.id, Question.prompt == item['prompt']))
            if q is None: q = Question(topic_id=topic.id, prompt=item['prompt'], choices=item['choices'], correct_choice_index=item['correct'], difficulty=item.get('difficulty', .35)); db.add(q)
            q.choices = item['choices']; q.correct_choice_index = item['correct']; q.difficulty = item.get('difficulty', .35)
            q.question_type = item.get('type', 'multiple_choice'); q.explanation = item['explanation']; q.distractor_explanations = item.get('distractor_explanations', [])
            q.learning_objective = item['learning_objective']; q.scoring_criteria = item.get('scoring_criteria', {'mode': 'exact_choice', 'points': 1})
            q.content_version = row.get('version', 1); q.provenance = item.get('provenance', row.get('provenance', 'ORBIT original content')); q.review_status = item.get('review_status', row.get('review_status', 'approved'))
            q_count += 1
    db.commit()
    return {'tracks': len(data['tracks']), 'modules': len(data['modules']), 'topics': len(data['topics']), 'questions_imported_or_updated': q_count}
