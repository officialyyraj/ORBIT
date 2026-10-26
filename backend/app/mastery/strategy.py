from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import MasteryEstimate, QuizResponse
from app.mastery.bkt import default_parameters, update_mastery
from app.mastery.dkt import DKTStrategy


class MasteryStrategy(ABC):
    @abstractmethod
    def estimate(self, db: Session, student_id: str, topic_id: str) -> float:
        ...


    @abstractmethod
    def update(
        self,
        db: Session,
        student_id: str,
        topic_id: str,
        correct: bool,
    ) -> tuple[float, str]:
        ...


class BKTStrategy(MasteryStrategy):
    def estimate(self, db, student_id, topic_id):
        row = db.scalar(
            select(MasteryEstimate).where(
                MasteryEstimate.student_id == student_id,
                MasteryEstimate.topic_id == topic_id,
            )
        )
        return row.p_mastery if row else default_parameters().p_init

    def update(self, db, student_id, topic_id, correct):
        row = db.scalar(
            select(MasteryEstimate).where(
                MasteryEstimate.student_id == student_id,
                MasteryEstimate.topic_id == topic_id,
            )
        )

        current = row.p_mastery if row else default_parameters().p_init
        value = update_mastery(current, correct)

        if row:
            row.p_mastery = value
            row.source = "bkt"
            row.last_updated = datetime.now(timezone.utc)
        else:
            row = MasteryEstimate(
                student_id=student_id,
                topic_id=topic_id,
                p_mastery=value,
                source="bkt",
            )
            db.add(row)

        db.flush()
        return value, "bkt"


class StrategySelector(MasteryStrategy):
    def __init__(self, dkt: DKTStrategy | None = None):
        self.bkt = BKTStrategy()
        self.dkt = dkt or DKTStrategy()

    def _checkpoint_compatible(self, db) -> bool:
        settings = get_settings()
        if not settings.dkt_checkpoint_path or not Path(settings.dkt_checkpoint_path).exists():
            return False
        if not hasattr(self.dkt, 'checkpoint_matches_graph'):
            return True
        try:
            return self.dkt.checkpoint_matches_graph(db)
        except Exception:
            return False

    def _has_enough_interactions(self, db, student_id):
        settings = get_settings()

        # Do not activate DKT without a trained checkpoint.
        # An untrained DKT model produces flat 0.5 mastery estimates
        # for every topic and would incorrectly replace BKT.
        if not settings.dkt_checkpoint_path:
            return False

        if not Path(settings.dkt_checkpoint_path).exists():
            return False

        if not self._checkpoint_compatible(db):
            return False

        count = db.scalar(
            select(func.count(QuizResponse.id)).where(
                QuizResponse.student_id == student_id
            )
        ) or 0

        return count >= settings.dkt_min_interactions

    def estimate(self, db, student_id, topic_id):
        if self._has_enough_interactions(db, student_id):
            try:
                return self.dkt.estimate(db, student_id, topic_id)
            except (NotImplementedError, RuntimeError):
                pass

        return self.bkt.estimate(db, student_id, topic_id)

    def update(self, db, student_id, topic_id, correct):
        if self._has_enough_interactions(db, student_id):
            try:
                value, source = self.dkt.update(
                    db,
                    student_id,
                    topic_id,
                    correct,
                )

                row = db.scalar(
                    select(MasteryEstimate).where(
                        MasteryEstimate.student_id == student_id,
                        MasteryEstimate.topic_id == topic_id,
                    )
                )

                if row:
                    row.p_mastery = value
                    row.source = source
                    row.last_updated = datetime.now(timezone.utc)
                else:
                    db.add(
                        MasteryEstimate(
                            student_id=student_id,
                            topic_id=topic_id,
                            p_mastery=value,
                            source=source,
                        )
                    )

                db.flush()
                return value, source

            except (NotImplementedError, RuntimeError):
                pass

        return self.bkt.update(db, student_id, topic_id, correct)
