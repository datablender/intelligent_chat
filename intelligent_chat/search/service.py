"""Search service — text search over concepts and messages with metadata filters."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from intelligent_chat.storage.models import Concept, ConceptTag, IngestSession, Message


class SearchResult:
    __slots__ = ("id", "title", "type", "description", "body", "confidence",
                 "visibility", "project_id", "source_session", "tags", "updated_at", "score")

    def __init__(self, concept: Concept, score: int = 0):
        self.id = concept.id
        self.title = concept.title
        self.type = concept.type
        self.description = concept.description
        self.body = concept.body
        self.confidence = concept.confidence
        self.visibility = concept.visibility
        self.project_id = concept.project_id
        self.source_session = concept.resource
        self.tags = [t.tag for t in concept.tags]
        self.updated_at = concept.updated_at
        self.score = score

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "description": self.description,
            "confidence": self.confidence,
            "visibility": self.visibility,
            "project_id": self.project_id,
            "tags": self.tags,
            "source_session": self.source_session,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "score": self.score,
        }


def search_concepts(
    db: Session,
    workspace_id: int,
    query: str,
    *,
    concept_type: str | None = None,
    tag: str | None = None,
    project_id: int | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = 20,
    include_project_ids: list[int] | None = None,
) -> list[SearchResult]:
    """Search concepts by text query with optional metadata filters.

    include_project_ids restricts results to workspace-visible concepts plus
    concepts scoped to the listed projects (access control enforcement).
    When None, all workspace concepts are returned (single-user / admin mode).
    """
    q = db.query(Concept).filter(Concept.workspace_id == workspace_id)

    # Visibility filter — show workspace-wide + concepts from accessible projects
    if include_project_ids is not None:
        q = q.filter(
            or_(
                Concept.visibility == "workspace",
                Concept.project_id.in_(include_project_ids),
            )
        )

    # Text search — title match scores 2, body match scores 1
    term = f"%{query}%"
    if query:
        q = q.filter(
            or_(
                Concept.title.ilike(term),
                Concept.description.ilike(term),
                Concept.body.ilike(term),
            )
        )

    if concept_type:
        q = q.filter(Concept.type == concept_type)

    if tag:
        q = q.join(ConceptTag, Concept.id == ConceptTag.concept_id).filter(
            ConceptTag.tag == tag
        )

    if project_id is not None:
        q = q.filter(Concept.project_id == project_id)

    if from_date:
        q = q.filter(Concept.updated_at >= from_date)

    if to_date:
        q = q.filter(Concept.updated_at <= to_date)

    concepts = q.limit(limit).all()

    # Simple relevance score: title match = 2 pts, body/description = 1 pt
    results = []
    term_lower = query.lower()
    for concept in concepts:
        score = 0
        if term_lower and term_lower in (concept.title or "").lower():
            score += 2
        if term_lower and term_lower in (concept.description or "").lower():
            score += 1
        if term_lower and term_lower in (concept.body or "").lower():
            score += 1
        results.append(SearchResult(concept, score))

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def search_sessions(
    db: Session,
    workspace_id: int,
    query: str,
    *,
    limit: int = 10,
) -> list[dict]:
    """Search message content and return matching sessions."""
    term = f"%{query}%"
    messages = (
        db.query(Message)
        .join(IngestSession, Message.session_id == IngestSession.id)
        .filter(
            IngestSession.workspace_id == workspace_id,
            Message.content.ilike(term),
        )
        .limit(limit * 5)
        .all()
    )

    # Deduplicate by session, return session summaries
    seen: set[str] = set()
    sessions: list[dict] = []
    for msg in messages:
        if msg.session_id not in seen:
            seen.add(msg.session_id)
            sess = db.get(IngestSession, msg.session_id)
            if sess:
                sessions.append({
                    "session_id": sess.id,
                    "source_type": sess.source_type,
                    "started_at": sess.started_at.isoformat() if sess.started_at else None,
                    "token_count": sess.token_count,
                    "status": sess.status,
                    "snippet": (msg.content or "")[:200],
                })
        if len(sessions) >= limit:
            break

    return sessions


def search_concepts_semantic(
    db: Session,
    workspace_id: int,
    query: str,
    *,
    limit: int = 20,
    min_score: float = 0.5,
    include_project_ids: list[int] | None = None,
) -> list[SearchResult]:
    """Semantic similarity search over concepts with stored embeddings.

    Loads all embedded concepts for the workspace, scores them via cosine
    similarity against the query embedding, and returns results above min_score
    ranked highest-first.  Concepts without embeddings are silently skipped.
    """
    from intelligent_chat.embeddings.service import cosine_similarity, generate_embedding

    query_vec = generate_embedding(query)

    q = db.query(Concept).filter(
        Concept.workspace_id == workspace_id,
        Concept.embedding.isnot(None),
    )
    if include_project_ids is not None:
        q = q.filter(
            or_(
                Concept.visibility == "workspace",
                Concept.project_id.in_(include_project_ids),
            )
        )

    concepts = q.all()
    scored: list[tuple[float, Concept]] = []
    for concept in concepts:
        vec = json.loads(concept.embedding)
        sim = cosine_similarity(query_vec, vec)
        if sim >= min_score:
            scored.append((sim, concept))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [SearchResult(concept, round(sim * 100)) for sim, concept in scored[:limit]]


def get_session_concepts(
    db: Session,
    workspace_id: int,
    session_id: str,
) -> list[SearchResult]:
    """Return all concepts extracted from a specific session."""
    concepts = (
        db.query(Concept)
        .filter(
            Concept.workspace_id == workspace_id,
            Concept.resource == f"session:{session_id}",
        )
        .all()
    )
    return [SearchResult(c) for c in concepts]
