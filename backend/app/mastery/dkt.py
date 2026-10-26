from __future__ import annotations

import hashlib
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


def _stable_topic_hash(topic_id: str, width: int) -> np.ndarray:
    digest = hashlib.sha256(topic_id.encode('utf-8')).digest()
    values = np.frombuffer(digest * ((width + len(digest) - 1) // len(digest)), dtype=np.uint8)[:width]
    return ((values.astype(np.float64) - 127.5) / 127.5).astype(np.float64)


class DKTStrategy:
    """A dependency-light recurrent DKT model with an explicit LSTM cell."""

    def __init__(self, checkpoint_path: str | None = None):
        self.hidden_size = get_settings().dkt_hidden_size
        self.learning_rate = get_settings().dkt_learning_rate
        self.topic_ids: list[str] = []
        self.embeddings = np.zeros((0, self.hidden_size), dtype=np.float64)
        self.w_input = np.zeros((4 * self.hidden_size, self.hidden_size + 1), dtype=np.float64)
        self.w_hidden = np.zeros((4 * self.hidden_size, self.hidden_size), dtype=np.float64)
        self.bias = np.zeros(4 * self.hidden_size, dtype=np.float64)
        self.output = np.zeros((0, self.hidden_size), dtype=np.float64)
        self.output_bias = np.zeros(0, dtype=np.float64)
        self.graph_fingerprint: str | None = None
        self.architecture = 'numpy_lstm'
        if checkpoint_path and Path(checkpoint_path).exists():
            self.load(checkpoint_path)

    @staticmethod
    def _graph_fingerprint_for_topics(topic_ids: list[str], edges: list[tuple[str, str]]) -> str:
        payload = {'topics': sorted(topic_ids), 'edges': sorted((sorted((left, right))) for left, right in edges)}
        encoded = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def _compute_graph_fingerprint(self, db: Session) -> str:
        topics = db.scalars(select(Topic).order_by(Topic.id)).all()
        topic_ids = [topic.id for topic in topics]
        edge_pairs = []
        for edge in db.scalars(select(TopicEdge)).all():
            if edge.prerequisite_id and edge.topic_id:
                edge_pairs.append((edge.prerequisite_id, edge.topic_id))
        return self._graph_fingerprint_for_topics(topic_ids, edge_pairs)

    def checkpoint_matches_graph(self, db: Session) -> bool:
        if not self.graph_fingerprint:
            return False
        return self.graph_fingerprint == self._compute_graph_fingerprint(db)

    def initialize_from_kst(self, db: Session) -> None:
        topics = db.scalars(select(Topic).order_by(Topic.id)).all()
        edges = db.scalars(select(TopicEdge)).all()
        self.topic_ids = [topic.id for topic in topics]
        index = {topic_id: i for i, topic_id in enumerate(self.topic_ids)}
        adjacency = np.zeros((len(self.topic_ids), len(self.topic_ids)), dtype=np.float64)
        for edge in edges:
            if edge.prerequisite_id in index and edge.topic_id in index:
                adjacency[index[edge.prerequisite_id], index[edge.topic_id]] = 1.0
        if not self.topic_ids:
            self.embeddings = np.zeros((0, self.hidden_size), dtype=np.float64)
        else:
            A = adjacency + adjacency.T + np.eye(len(self.topic_ids), dtype=np.float64)
            weights, vectors = np.linalg.eigh(A)
            order = np.argsort(weights)[::-1]
            width = min(self.hidden_size, len(self.topic_ids))
            structure = vectors[:, order[:width]] * np.sqrt(np.maximum(np.abs(weights[order[:width]]), 1e-3))
            for column in range(structure.shape[1]):
                values = structure[:, column]
                pivot = int(np.argmax(np.abs(values)))
                if values[pivot] < 0:
                    structure[:, column] *= -1
            hash_component = np.stack([_stable_topic_hash(topic_id, self.hidden_size) for topic_id in self.topic_ids], axis=0)
            if structure.shape[1] < self.hidden_size:
                filler = hash_component[:, : self.hidden_size - structure.shape[1]]
                embedding = np.hstack([structure, filler])
            else:
                embedding = structure[:, : self.hidden_size]
            if embedding.shape[1] != self.hidden_size:
                embedding = np.pad(embedding, ((0, 0), (0, self.hidden_size - embedding.shape[1])))
            self.embeddings = embedding.astype(np.float64)
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            self.embeddings = self.embeddings / np.maximum(norms, 1e-9)
        self.w_input = np.zeros((4 * self.hidden_size, self.hidden_size + 1), dtype=np.float64)
        self.w_hidden = np.zeros((4 * self.hidden_size, self.hidden_size), dtype=np.float64)
        for gate in range(4):
            start = gate * self.hidden_size
            self.w_input[start:start + self.hidden_size, :self.hidden_size] = np.eye(self.hidden_size) * (0.25 if gate != 1 else 0.35)
            self.w_hidden[start:start + self.hidden_size, :] = np.eye(self.hidden_size) * (0.15 if gate != 1 else 0.25)
        self.bias = np.zeros(4 * self.hidden_size, dtype=np.float64)
        self.bias[self.hidden_size:2 * self.hidden_size] = 0.7
        self.output = np.ones((len(self.topic_ids), self.hidden_size), dtype=np.float64) / max(1, self.hidden_size)
        self.output_bias = np.zeros(len(self.topic_ids), dtype=np.float64)
        self.graph_fingerprint = self._graph_fingerprint_for_topics(self.topic_ids, [(edge.prerequisite_id, edge.topic_id) for edge in edges if edge.prerequisite_id in index and edge.topic_id in index])

    def _ensure_initialized(self, db: Session) -> None:
        if not self.topic_ids:
            self.initialize_from_kst(db)

    def _topic_index(self, topic_id: str) -> int:
        if topic_id not in self.topic_ids:
            return -1
        return self.topic_ids.index(topic_id)

    def _topic_embedding(self, topic_id: str) -> np.ndarray:
        index = self._topic_index(topic_id)
        if index < 0:
            return np.zeros(self.hidden_size, dtype=np.float64)
        return self.embeddings[index]

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
        topic_index = self._topic_index(topic_id)
        if topic_index < 0:
            return 0.5
        topic_signal = float(np.dot(self.output[topic_index], hidden) + 0.25 * np.dot(self._topic_embedding(topic_id), hidden) + self.output_bias[topic_index])
        return float(np.clip(_sigmoid(topic_signal), 0.0, 1.0))

    def update(self, db: Session, student_id: str, topic_id: str, correct: bool) -> tuple[float, str]:
        self._ensure_initialized(db)
        return self.estimate(db, student_id, topic_id), 'dkt'

    def _backward_step(self, hidden_prev: np.ndarray, cell_prev: np.ndarray, x: np.ndarray, grad_hidden_next: np.ndarray, grad_cell_next: np.ndarray):
        gates = self.w_input @ x + self.w_hidden @ hidden_prev + self.bias
        input_gate = _sigmoid(gates[:self.hidden_size])
        forget_gate = _sigmoid(gates[self.hidden_size:2 * self.hidden_size])
        candidate = np.tanh(gates[2 * self.hidden_size:3 * self.hidden_size])
        output_gate = _sigmoid(gates[3 * self.hidden_size:])
        cell = forget_gate * cell_prev + input_gate * candidate
        hidden = output_gate * np.tanh(cell)
        grad_cell = grad_hidden_next * output_gate * (1.0 - np.tanh(cell) ** 2) + grad_cell_next
        grad_output_gate = grad_hidden_next * np.tanh(cell) * output_gate * (1.0 - output_gate)
        grad_forget = cell_prev * grad_cell * forget_gate * (1.0 - forget_gate)
        grad_input = candidate * grad_cell * input_gate * (1.0 - input_gate)
        grad_candidate = input_gate * grad_cell * (1.0 - candidate ** 2)
        grad_gates = np.concatenate([grad_input, grad_forget, grad_candidate, grad_output_gate])
        dW_input = np.outer(grad_gates, x)
        dW_hidden = np.outer(grad_gates, hidden_prev)
        dbias = grad_gates.copy()
        grad_x = self.w_input.T @ grad_gates
        grad_hidden_prev = self.w_hidden.T @ grad_gates
        grad_cell_prev = grad_cell * forget_gate
        return dW_input, dW_hidden, dbias, grad_hidden_prev, grad_cell_prev, grad_x

    def fit(self, db: Session, epochs: int = 8) -> dict:
        self._ensure_initialized(db)
        responses = db.scalars(select(QuizResponse).order_by(QuizResponse.student_id, QuizResponse.responded_at, QuizResponse.id)).all()
        history_by_student: dict[str, list] = {}
        for response in responses:
            history_by_student.setdefault(response.student_id, []).append(response)
        losses = []
        for epoch in range(max(1, epochs)):
            epoch_loss = 0.0
            for sequence in history_by_student.values():
                hidden = np.zeros(self.hidden_size, dtype=np.float64)
                cell = np.zeros(self.hidden_size, dtype=np.float64)
                step_cache = []
                for response in sequence:
                    topic_index = self._topic_index(response.topic_id)
                    if topic_index < 0:
                        continue
                    target = 1.0 if response.correct else 0.0
                    x = np.concatenate([self._topic_embedding(response.topic_id), np.array([target], dtype=np.float64)])
                    hidden_pre = hidden.copy()
                    cell_pre = cell.copy()
                    hidden, cell = self._step(hidden, cell, x)
                    prediction = float(_sigmoid(np.dot(self.output[topic_index], hidden) + self.output_bias[topic_index]))
                    error = prediction - target
                    epoch_loss += -(target * np.log(max(prediction, 1e-9)) + (1 - target) * np.log(max(1 - prediction, 1e-9)))
                    grad_output = error * hidden
                    self.output[topic_index] -= self.learning_rate * grad_output
                    self.output_bias[topic_index] -= self.learning_rate * error
                    grad_hidden = error * self.output[topic_index]
                    dW_input, dW_hidden, dbias, grad_hidden_prev, grad_cell_prev, _ = self._backward_step(hidden_pre, cell_pre, x, grad_hidden, np.zeros(self.hidden_size, dtype=np.float64))
                    self.w_input -= self.learning_rate * dW_input
                    self.w_hidden -= self.learning_rate * dW_hidden
                    self.bias -= self.learning_rate * dbias
                    self.w_input = np.clip(self.w_input, -5.0, 5.0)
                    self.w_hidden = np.clip(self.w_hidden, -5.0, 5.0)
                    self.bias = np.clip(self.bias, -5.0, 5.0)
                    step_cache.append((hidden_pre, cell_pre, x, grad_hidden_prev, grad_cell_prev))
            losses.append(epoch_loss)
        return {'epochs': max(1, epochs), 'interactions': len(responses), 'final_loss': float(losses[-1] if losses else 0.0), 'topics': len(self.topic_ids), 'architecture': 'numpy_lstm'}

    def save(self, path: str) -> None:
        payload = {'topic_ids': self.topic_ids, 'embeddings': self.embeddings.tolist(), 'w_input': self.w_input.tolist(), 'w_hidden': self.w_hidden.tolist(), 'bias': self.bias.tolist(), 'output': self.output.tolist(), 'output_bias': self.output_bias.tolist(), 'graph_fingerprint': self.graph_fingerprint, 'architecture': 'numpy_lstm'}
        Path(path).write_text(json.dumps(payload))

    def load(self, path: str) -> None:
        payload = json.loads(Path(path).read_text())
        self.topic_ids = payload['topic_ids']
        self.embeddings = np.array(payload['embeddings'], dtype=np.float64)
        self.w_input = np.array(payload['w_input'], dtype=np.float64)
        self.w_hidden = np.array(payload['w_hidden'], dtype=np.float64)
        self.bias = np.array(payload['bias'], dtype=np.float64)
        self.output = np.array(payload['output'], dtype=np.float64)
        self.output_bias = np.array(payload.get('output_bias', np.zeros(len(self.topic_ids))), dtype=np.float64)
        if self.output.ndim == 1:
            self.output = np.tile(self.output.reshape(1, -1), (len(self.topic_ids), 1))
        self.output_bias = np.asarray(self.output_bias, dtype=np.float64)
        if self.output_bias.size == 0:
            self.output_bias = np.zeros(len(self.topic_ids), dtype=np.float64)
        self.graph_fingerprint = payload.get('graph_fingerprint')
        self.architecture = payload.get('architecture', 'numpy_lstm')
