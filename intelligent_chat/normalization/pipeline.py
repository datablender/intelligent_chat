"""LLM normalization pipeline — extracts OKF concept pages from raw transcripts."""

from __future__ import annotations

from sqlalchemy.orm import Session

from intelligent_chat.normalization.llm_client import call_save_knowledge
from intelligent_chat.normalization.prompts import (
    SAVE_KNOWLEDGE_TOOL,
    build_system_prompt,
    build_user_prompt,
    format_transcript,
    load_conventions,
)
from intelligent_chat.storage.models import (
    Concept,
    ConceptTag,
    Evidence,
    IngestSession,
    Relationship,
)


def _get_concept_index(db: Session, workspace_id: int) -> list[dict]:
    concepts = db.query(Concept).filter_by(workspace_id=workspace_id).all()
    return [
        {"id": c.id, "title": c.title, "type": c.type, "description": c.description}
        for c in concepts
    ]


def _resolve_concept_id(title: str, title_map: dict[str, int], db: Session, workspace_id: int) -> int | None:
    if title in title_map:
        return title_map[title]
    concept = db.query(Concept).filter_by(workspace_id=workspace_id, title=title).first()
    if concept:
        title_map[title] = concept.id
        return concept.id
    return None


def normalize_session(
    session_envelope: dict,
    db: Session,
    workspace_id: int,
    db_session_id: str,
) -> dict:
    """Run LLM normalization on a session envelope. Writes concepts and relationships to DB.

    Returns a summary dict: {concepts_created, concepts_updated, relationships_created}.
    """
    # Resolve the project_id so project-scoped concepts can be tagged correctly
    ingest_sess = db.get(IngestSession, db_session_id)
    session_project_id: int | None = ingest_sess.project_id if ingest_sess else None

    conventions = load_conventions()
    transcript = format_transcript(session_envelope["messages"])
    concept_index = _get_concept_index(db, workspace_id)

    system_prompt = build_system_prompt(conventions)
    user_prompt = build_user_prompt(
        transcript=transcript,
        project_name=session_envelope.get("project_name", "unknown"),
        session_id=session_envelope["session_id"],
        concept_index=concept_index,
    )

    tool_input = call_save_knowledge(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=SAVE_KNOWLEDGE_TOOL,
    )

    if not tool_input:
        return {"concepts_created": 0, "concepts_updated": 0, "relationships_created": 0}

    concepts_created = 0
    concepts_updated = 0
    relationships_created = 0

    # Map title → concept id for relationship resolution within this batch
    title_map: dict[str, int] = {c["title"]: c["id"] for c in concept_index}

    # --- Process concepts ---
    for item in tool_input.get("concepts", []):
        action = item.get("action", "create")
        tags: list[str] = item.get("tags") or []

        scope = item.get("scope", "workspace")
        # project-scoped concepts are tied to the session's project and only visible to project members
        concept_project_id = session_project_id if scope == "project" else None
        concept_visibility = "project" if scope == "project" else "workspace"

        if action == "update" and item.get("existing_id"):
            concept = db.get(Concept, item["existing_id"])
            if concept and concept.workspace_id == workspace_id:
                concept.title = item["title"]
                concept.description = item.get("description")
                concept.type = item["type"]
                concept.body = item.get("body")
                concept.confidence = item.get("confidence", "extracted")
                concept.project_id = concept_project_id
                concept.visibility = concept_visibility
                # Replace tags
                db.query(ConceptTag).filter_by(concept_id=concept.id).delete()
                for tag in tags:
                    db.add(ConceptTag(concept_id=concept.id, tag=tag))
                title_map[concept.title] = concept.id
                concepts_updated += 1
        else:
            concept = Concept(
                workspace_id=workspace_id,
                project_id=concept_project_id,
                title=item["title"],
                description=item.get("description"),
                type=item["type"],
                body=item.get("body"),
                confidence=item.get("confidence", "extracted"),
                visibility=concept_visibility,
                resource=f"session:{db_session_id}",
            )
            db.add(concept)
            db.flush()  # get concept.id
            for tag in tags:
                db.add(ConceptTag(concept_id=concept.id, tag=tag))
            title_map[concept.title] = concept.id
            concepts_created += 1

    db.flush()

    # --- Process relationships ---
    for rel in tool_input.get("relationships", []):
        source_id = _resolve_concept_id(rel["source_title"], title_map, db, workspace_id)
        target_id = _resolve_concept_id(rel["target_title"], title_map, db, workspace_id)

        if not source_id or not target_id:
            continue

        evidence_id: int | None = None
        snippet = rel.get("evidence_snippet")
        if snippet:
            evidence = Evidence(
                workspace_id=workspace_id,
                session_id=db_session_id,
                snippet=snippet,
                citation=f"session:{db_session_id}",
            )
            db.add(evidence)
            db.flush()
            evidence_id = evidence.id

        db.add(Relationship(
            workspace_id=workspace_id,
            source_concept_id=source_id,
            target_concept_id=target_id,
            relation_type=rel["relation_type"],
            confidence=rel.get("confidence", "extracted"),
            evidence_id=evidence_id,
        ))
        relationships_created += 1

    # Mark session normalized
    sess = db.get(IngestSession, db_session_id)
    if sess:
        sess.status = "normalized"

    db.commit()

    return {
        "concepts_created": concepts_created,
        "concepts_updated": concepts_updated,
        "relationships_created": relationships_created,
    }
