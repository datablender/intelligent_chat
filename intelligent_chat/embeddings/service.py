"""Embedding generation and bulk indexing for semantic search."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

from openai import OpenAI

from intelligent_chat import config
from intelligent_chat.storage.models import Concept

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _client() -> OpenAI:
    if not config.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set — required for semantic search. "
            "Add it to your .env file."
        )
    return OpenAI(api_key=config.OPENAI_API_KEY)


def generate_embedding(text: str) -> list[float]:
    """Call the OpenAI embedding API and return the float vector."""
    resp = _client().embeddings.create(model=config.EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def _concept_text(concept: Concept) -> str:
    parts = [concept.title]
    if concept.description:
        parts.append(concept.description)
    return ". ".join(parts)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_concept(db: Session, concept_id: int) -> bool:
    """Generate and store an embedding for a single concept. Returns True if stored."""
    concept = db.get(Concept, concept_id)
    if not concept:
        return False
    vec = generate_embedding(_concept_text(concept))
    concept.embedding = json.dumps(vec)
    db.commit()
    return True


def embed_all_concepts(db: Session, workspace_id: int, *, force: bool = False) -> int:
    """Generate embeddings for all concepts in the workspace.

    By default only processes concepts that have no embedding yet.
    Pass force=True to regenerate all embeddings.
    """
    q = db.query(Concept).filter(Concept.workspace_id == workspace_id)
    if not force:
        q = q.filter(Concept.embedding.is_(None))
    concepts = q.all()

    for concept in concepts:
        vec = generate_embedding(_concept_text(concept))
        concept.embedding = json.dumps(vec)

    db.commit()
    return len(concepts)
