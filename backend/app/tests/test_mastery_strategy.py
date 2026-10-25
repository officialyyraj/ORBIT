from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Question, QuizResponse, Topic, User
from app.mastery.strategy import StrategySelector


class UnavailableDKT:
    def estimate(self, *args, **kwargs):
        raise AssertionError('DKT must not be used without a checkpoint')

    def update(self, *args, **kwargs):
        raise AssertionError('DKT must not be used without a checkpoint')


def test_bkt_remains_active_after_fifty_responses_without_dkt_checkpoint(monkeypatch):
    monkeypatch.setattr(
        'app.mastery.strategy.get_settings',
        lambda: SimpleNamespace(dkt_checkpoint_path=None, dkt_min_interactions=50),
    )
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        learner = User(email='learner@example.test', password_hash='hash')
        correct_topic = Topic(name='Correct topic', description='', estimated_minutes=10)
        wrong_topic = Topic(name='Wrong topic', description='', estimated_minutes=10)
        session.add_all([learner, correct_topic, wrong_topic])
        session.flush()
        question = Question(
            topic_id=correct_topic.id,
            prompt='Question?',
            choices=['a', 'b'],
            correct_choice_index=0,
            difficulty=0.1,
        )
        session.add(question)
        session.flush()
        session.add_all([
            QuizResponse(student_id=learner.id, question_id=question.id, topic_id=correct_topic.id, correct=True)
            for _ in range(50)
        ])
        session.flush()

        selector = StrategySelector(dkt=UnavailableDKT())
        assert not selector._has_enough_interactions(session, learner.id)

        correct_mastery, correct_source = selector.update(session, learner.id, correct_topic.id, True)
        wrong_mastery, wrong_source = selector.update(session, learner.id, wrong_topic.id, False)

        assert correct_source == wrong_source == 'bkt'
        assert correct_mastery != wrong_mastery
        assert correct_mastery != 0.5
        assert wrong_mastery != 0.5
    finally:
        session.close()
        engine.dispose()
