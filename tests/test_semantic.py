"""Tests for semantic search — embedding generation and cosine similarity."""

from __future__ import annotations

import json
import math
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from intelligent_chat.embeddings.service import cosine_similarity, embed_concept
from intelligent_chat.search.service import search_concepts_semantic
from intelligent_chat.storage.models import Base, Concept, User, Workspace


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    yield session
    session.close()


def _seed(db: Session) -> tuple[int, list[int]]:
    user = User(email="a@x.com", name="A", role="admin")
    db.add(user)
    db.flush()
    ws = Workspace(name="test-ws", owner_id=user.id, visibility="private")
    db.add(ws)
    db.flush()
    c1 = Concept(
        workspace_id=ws.id, title="Python type hints",
        description="Static typing in Python", type="pattern",
        confidence="extracted", visibility="workspace",
    )
    c2 = Concept(
        workspace_id=ws.id, title="Docker deployment",
        description="Containerising apps", type="tool",
        confidence="extracted", visibility="workspace",
    )
    db.add_all([c1, c2])
    db.commit()
    return ws.id, [c1.id, c2.id]


def _unit_vec(seed: float, dims: int = 8) -> list[float]:
    raw = [math.sin(seed + i) for i in range(dims)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        v = _unit_vec(1.0)
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors_score_zero(self):
        assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_parallel_non_unit_vectors_score_one(self):
        a = [2.0, 4.0]
        b = [1.0, 2.0]
        assert abs(cosine_similarity(a, b) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# embed_concept
# ---------------------------------------------------------------------------

class TestEmbedConcept:
    def test_stores_embedding_as_json(self, db):
        ws_id, ids = _seed(db)
        fake_vec = _unit_vec(42.0)
        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=fake_vec):
            result = embed_concept(db, ids[0])
        assert result is True
        stored = json.loads(db.get(Concept, ids[0]).embedding)
        assert abs(stored[0] - fake_vec[0]) < 1e-9

    def test_missing_concept_returns_false(self, db):
        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=[0.1]):
            result = embed_concept(db, 999999)
        assert result is False

    def test_overwrites_existing_embedding(self, db):
        ws_id, ids = _seed(db)
        first_vec = _unit_vec(1.0)
        second_vec = _unit_vec(2.0)
        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=first_vec):
            embed_concept(db, ids[0])
        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=second_vec):
            embed_concept(db, ids[0])
        stored = json.loads(db.get(Concept, ids[0]).embedding)
        assert abs(stored[0] - second_vec[0]) < 1e-9


# ---------------------------------------------------------------------------
# search_concepts_semantic
# ---------------------------------------------------------------------------

class TestSemanticSearch:
    def test_returns_closest_concept_first(self, db):
        ws_id, ids = _seed(db)
        query_vec = _unit_vec(1.0)
        close_vec = _unit_vec(1.1)   # near query
        far_vec = _unit_vec(50.0)    # far from query

        db.get(Concept, ids[0]).embedding = json.dumps(close_vec)
        db.get(Concept, ids[1]).embedding = json.dumps(far_vec)
        db.commit()

        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=query_vec):
            results = search_concepts_semantic(db, ws_id, "typing", min_score=0.0)

        assert results[0].id == ids[0]

    def test_min_score_filters_low_similarity(self, db):
        ws_id, ids = _seed(db)
        query_vec = _unit_vec(1.0)
        db.get(Concept, ids[0]).embedding = json.dumps(_unit_vec(50.0))
        db.commit()

        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=query_vec):
            results = search_concepts_semantic(db, ws_id, "anything", min_score=0.99)

        assert results == []

    def test_skips_concepts_without_embeddings(self, db):
        ws_id, ids = _seed(db)
        query_vec = _unit_vec(1.0)
        db.get(Concept, ids[0]).embedding = json.dumps(query_vec)
        # ids[1] has no embedding
        db.commit()

        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=query_vec):
            results = search_concepts_semantic(db, ws_id, "query", min_score=0.0)

        assert len(results) == 1
        assert results[0].id == ids[0]

    def test_score_is_percentage(self, db):
        ws_id, ids = _seed(db)
        query_vec = _unit_vec(1.0)
        db.get(Concept, ids[0]).embedding = json.dumps(query_vec)
        db.commit()

        with patch("intelligent_chat.embeddings.service.generate_embedding", return_value=query_vec):
            results = search_concepts_semantic(db, ws_id, "query", min_score=0.0)

        assert results[0].score == 100  # identical vector → 100%
