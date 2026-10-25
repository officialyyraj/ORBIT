from __future__ import annotations

import json
from pathlib import Path
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db.models import QuizResponse, Topic, TopicEdge

class DKTNotImplemented(Exception):
    pass


def _sigmoid(value: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -30, 30)))


class DKTStrategy:
    """A dependency-light recurrent DKT model with an explicit LSTM cell.

    Topic embeddings are initialized from the KST identity, adjacency, and
    two-hop adjacency features. The model is trained offline and persisted as a
    JSON checkpoint; request-time inference replays a student's sequence.
    """

    def __init__(self, checkpoint_path: str | None = None):
        self.hidden_size = get_settings().dkt_hidden_size
        self.learning_rate = get_settings().dkt_learning_rate
        self.topic_ids: list[str] = []
        self.embeddings = np.zeros((0, self.hidden_size), dtype=np.float64)
        self.w_input = np.zeros((4 * self.hidden_size, self.hidden_size + 1), dtype=np.float64)
        self.w_hidden = np.zeros((4 * self.hidden_size, self.hidden_size), dtype=np.float64)
        self.bias = np.zeros(4 * self.hidden_size, dtype=np.float64)
        self.output = np.zeros(self.hidden_size, dtype=np.float64)
        self.output_bias = 0.0
        if checkpoint_path and Path(checkpoint_path).exists():
            self.load(checkpoint_path)

    def initialize_from_kst(self, db: Session) -> None:
        topics = db.scalars(select(Topic).order_by(Topic.id)).all()
        edges = db.scalars(select(TopicEdge)).all()
        self.topic_ids = [topic.id for topic in topics]
        index = {topic_id: i for i, topic_id in enumerate(self.topic_ids)}
        adjacency = np.zeros((len(self.topic_ids), len(self.topic_ids)), dtype=np.float64)
        for edge in edges:
            if edge.prerequisite_id in index and edge.topic_id in index:
                adjacency[index[edge.prerequisite_id], index[edge.topic_id]] = 1.0
        features = np.concatenate([np.eye(len(self.topic_ids)), adjacency, adjacency @ adjacency], axis=1) if self.topic_ids else np.zeros((0, 0))
        self.embeddings = np.zeros((len(self.topic_ids), self.hidden_size), dtype=np.float64)
        if features.size:
            width = min(self.hidden_size, features.shape[1])
            self.embeddings[:, :width] = features[:, :width]
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            self.embeddings = self.embeddings / np.maximum(norms, 1e-9)
        self.w_input = np.zeros((4 * self.hidden_size, self.hidden_size + 1), dtype=np.float64)
        self.w_hidden = np.zeros((4 * self.hidden_size, self.hidden_size), dtype=np.float64)
        # Deterministic LSTM initialization. Each gate has a stable identity
        # component, and the forget gate starts slightly open for sequence memory.
        for gate in range(4):
            start = gate * self.hidden_size
            self.w_input[start:start + self.hidden_size, :self.hidden_size] = np.eye(self.hidden_size) * (0.25 if gate != 1 else 0.35)
            self.w_hidden[start:start + self.hidden_size, :] = np.eye(self.hidden_size) * (0.15 if gate != 1 else 0.25)
        self.bias = np.zeros(4 * self.hidden_size, dtype=np.float64)
        self.bias[self.hidden_size:2 * self.hidden_size] = 0.7
        self.output = np.ones(self.hidden_size, dtype=np.float64) / max(1, self.hidden_size)

    def _ensure_initialized(self, db: Session) -> None:
        if not self.topic_ids:
            self.initialize_from_kst(db)

    def _topic_embedding(self, topic_id: str) -> np.ndarray:
        if topic_id not in self.topic_ids:
            return np.zeros(self.hidden_size, dtype=np.float64)
        return self.embeddings[self.topic_ids.index(topic_id)]

    def _sequence(self, db: Session, student_id: str):
        return db.scalars(select(QuizResponse).where(QuizResponse.student_id == student_id).order_by(QuizResponse.responded_at, QuizResponse.id)).all()

    def _step(self, hidden: np.ndarray, cell: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        gates = self.w_input @ x + self.w_hidden @ hidden + self.bias
        input_gate = _sigmoid(gates[:self.hidden_size])
        forget_gate = _sigmoid(gates[self.hidden_size:2 * self.hidden_size])
        candidate = np.tanh(gates[2 * self.hidden_size:3 * self.hidden_size])
        output_gate = _sigmoid(gates[3 * self.hidden_size:])
        cell = forget_gate * cell + input_gate * candidate
        hidden = output_gate * np.tanh(cell)
        return hidden, cell

    def _replay(self, responses) -> np.ndarray:
        hidden = np.zeros(self.hidden_size, dtype=np.float64)
        cell = np.zeros(self.hidden_size, dtype=np.float64)
        for response in responses:
            x = np.concatenate([self._topic_embedding(response.topic_id), np.array([1.0 if response.correct else 0.0])])
            hidden, cell = self._step(hidden, cell, x)
        return hidden

    def estimate(self, db: Session, student_id: str, topic_id: str) -> float:
        self._ensure_initialized(db)
        hidden = self._replay(self._sequence(db, student_id))
        topic_signal = float(np.dot(self.output, hidden) + 0.25 * np.dot(self._topic_embedding(topic_id), hidden) + self.output_bias)
        return float(np.clip(_sigmoid(topic_signal), 0.0, 1.0))

    def update(self, db: Session, student_id: str, topic_id: str, correct: bool) -> tuple[float, str]:
        self._ensure_initialized(db)
        return self.estimate(db, student_id, topic_id), 'dkt'

    def fit(self, db: Session, epochs: int = 8) -> dict:
        self._ensure_initialized(db)
        responses = db.scalars(select(QuizResponse).order_by(QuizResponse.student_id, QuizResponse.responded_at, QuizResponse.id)).all()
        history_by_student: dict[str, list] = {}
        for response in responses:
            history_by_student.setdefault(response.student_id, []).append(response)
        losses = []
        for _ in range(max(1, epochs)):
            epoch_loss = 0.0
            for sequence in history_by_student.values():
                hidden = np.zeros(self.hidden_size, dtype=np.float64)
                cell = np.zeros(self.hidden_size, dtype=np.float64)
                for response in sequence:
                    prediction = float(_sigmoid(np.dot(self.output, hidden) + self.output_bias))
                    target = 1.0 if response.correct else 0.0
                    error = prediction - target
                    epoch_loss += -(target * np.log(max(prediction, 1e-9)) + (1 - target) * np.log(max(1 - prediction, 1e-9)))
                    self.output -= self.learning_rate * error * hidden
                    self.output_bias -= self.learning_rate * error
                    x = np.concatenate([self._topic_embedding(response.topic_id), np.array([target])])
                    hidden, cell = self._step(hidden, cell, x)
            losses.append(epoch_loss)
        return {'epochs': max(1, epochs), 'interactions': len(responses), 'final_loss': float(losses[-1] if losses else 0.0), 'topics': len(self.topic_ids), 'architecture': 'numpy_lstm'}

    def save(self, path: str) -> None:
        payload = {'topic_ids': self.topic_ids, 'embeddings': self.embeddings.tolist(), 'w_input': self.w_input.tolist(), 'w_hidden': self.w_hidden.tolist(), 'bias': self.bias.tolist(), 'output': self.output.tolist(), 'output_bias': self.output_bias, 'architecture': 'numpy_lstm'}
        Path(path).write_text(json.dumps(payload))

    def load(self, path: str) -> None:
        payload = json.loads(Path(path).read_text())
        self.topic_ids = payload['topic_ids']
        self.embeddings = np.array(payload['embeddings'], dtype=np.float64)
        self.w_input = np.array(payload['w_input'], dtype=np.float64)
        self.w_hidden = np.array(payload['w_hidden'], dtype=np.float64)
        self.bias = np.array(payload['bias'], dtype=np.float64)
        self.output = np.array(payload['output'], dtype=np.float64)
        self.output_bias = float(payload['output_bias'])
