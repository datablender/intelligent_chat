"""Permission-aware concepts and search router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from intelligent_chat.api.deps import CurrentUser, accessible_project_ids, get_db
from intelligent_chat.api.schemas import AuditLogOut, ConceptOut, SearchResponse
from intelligent_chat.search.service import (
    get_session_concepts,
    search_concepts,
    search_concepts_semantic,
)
from intelligent_chat.storage.models import AuditLog, Concept

router = APIRouter(tags=["concepts"])


@router.get("/workspaces/{workspace_id}/concepts/search", response_model=SearchResponse)
def search(
    workspace_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    q: str = Query(default="", description="Search text"),
    concept_type: str | None = Query(default=None, alias="type"),
    tag: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    semantic: bool = Query(default=False, description="Use semantic (embedding) search"),
    min_score: float = Query(default=0.5, description="Min cosine similarity for semantic search"),
):
    """Search concepts with access control enforced.

    Set semantic=true to use vector similarity search (requires OPENAI_API_KEY and ichat embed).
    """
    proj_ids = accessible_project_ids(db, workspace_id, user.id)

    if semantic:
        results = search_concepts_semantic(
            db,
            workspace_id=workspace_id,
            query=q,
            limit=limit,
            min_score=min_score,
            include_project_ids=proj_ids,
        )
    else:
        results = search_concepts(
            db,
            workspace_id=workspace_id,
            query=q,
            concept_type=concept_type,
            tag=tag,
            project_id=project_id,
            limit=limit,
            include_project_ids=proj_ids,
        )
    return SearchResponse(total=len(results), results=[r.to_dict() for r in results])


@router.get("/workspaces/{workspace_id}/concepts/{concept_id}", response_model=ConceptOut)
def get_concept(
    workspace_id: int,
    concept_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Fetch a single concept with visibility enforcement."""
    concept = db.get(Concept, concept_id)
    if not concept or concept.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Concept not found")

    # Enforce visibility
    if concept.visibility == "project" and concept.project_id:
        proj_ids = accessible_project_ids(db, workspace_id, user.id)
        if proj_ids is not None and concept.project_id not in proj_ids:
            raise HTTPException(status_code=403, detail="Access denied")

    return ConceptOut(
        id=concept.id,
        title=concept.title,
        type=concept.type,
        description=concept.description,
        confidence=concept.confidence,
        visibility=concept.visibility,
        project_id=concept.project_id,
        tags=[t.tag for t in concept.tags],
        source_session=concept.resource,
        updated_at=concept.updated_at,
    )


@router.get("/workspaces/{workspace_id}/sessions/{session_id}/concepts", response_model=SearchResponse)
def session_concepts(
    workspace_id: int,
    session_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """List all concepts extracted from a specific session."""
    results = get_session_concepts(db, workspace_id=workspace_id, session_id=session_id)
    return SearchResponse(total=len(results), results=[r.to_dict() for r in results])


@router.get("/workspaces/{workspace_id}/audit-log", response_model=list[AuditLogOut])
def audit_log(
    workspace_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    limit: int = Query(default=50, le=200),
):
    """Return recent audit log entries for the workspace."""
    entries = (
        db.query(AuditLog)
        .filter_by(workspace_id=workspace_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return entries
