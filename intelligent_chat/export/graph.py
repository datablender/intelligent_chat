"""Graph exporter — produces Graphify-compatible graph.json from the database."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from intelligent_chat.storage.models import Concept, IngestSession, Project, Relationship


def export_graph(
    db: Session,
    workspace_id: int,
    output_path: Path,
    *,
    project_ids: list[int] | None = None,
) -> dict:
    """Export the knowledge graph as a Graphify-compatible graph.json file.

    Nodes: concepts, sessions, projects.
    Edges: relationship records with type and confidence.

    project_ids restricts concept nodes to workspace-visible + listed projects.
    When None, all workspace concepts are included (admin / single-user mode).

    Returns: {nodes: int, edges: int, output_path: str}
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    # --- Concept nodes ---
    q = db.query(Concept).filter(Concept.workspace_id == workspace_id)
    if project_ids is not None:
        from sqlalchemy import or_
        q = q.filter(
            or_(
                Concept.visibility == "workspace",
                Concept.project_id.in_(project_ids),
            )
        )
    concepts = q.all()
    concept_ids = {c.id for c in concepts}

    for c in concepts:
        nodes.append({
            "id": f"concept:{c.id}",
            "label": c.title,
            "type": c.type,
            "properties": {
                "description": c.description,
                "confidence": c.confidence,
                "visibility": c.visibility,
                "project_id": c.project_id,
                "tags": [t.tag for t in c.tags],
                "resource": c.resource,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            },
        })

    # --- Project nodes ---
    projects = db.query(Project).filter(Project.workspace_id == workspace_id).all()
    project_node_ids = {p.id for p in projects}
    for p in projects:
        nodes.append({
            "id": f"project:{p.id}",
            "label": p.name,
            "type": "project",
            "properties": {
                "description": p.description,
                "visibility": p.visibility,
            },
        })

    # --- Session nodes (lightweight — just metadata) ---
    sessions = (
        db.query(IngestSession)
        .filter(IngestSession.workspace_id == workspace_id)
        .all()
    )
    for s in sessions:
        nodes.append({
            "id": f"session:{s.id}",
            "label": s.id[:12],
            "type": "session",
            "properties": {
                "source_type": s.source_type,
                "token_count": s.token_count,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "project_id": s.project_id,
            },
        })

    # --- Relationship edges (concept → concept) ---
    rels = (
        db.query(Relationship)
        .filter(Relationship.workspace_id == workspace_id)
        .all()
    )
    for rel in rels:
        if rel.source_concept_id not in concept_ids or rel.target_concept_id not in concept_ids:
            continue
        edges.append({
            "source": f"concept:{rel.source_concept_id}",
            "target": f"concept:{rel.target_concept_id}",
            "type": rel.relation_type,
            "confidence": rel.confidence,
            "id": f"rel:{rel.id}",
        })

    # --- Session → project edges ---
    for s in sessions:
        if s.project_id and s.project_id in project_node_ids:
            edges.append({
                "source": f"session:{s.id}",
                "target": f"project:{s.project_id}",
                "type": "belongs_to",
                "confidence": "extracted",
                "id": f"sess-proj:{s.id}",
            })

    # --- Concept → project edges (for project-scoped concepts) ---
    for c in concepts:
        if c.project_id and c.project_id in project_node_ids:
            edges.append({
                "source": f"concept:{c.id}",
                "target": f"project:{c.project_id}",
                "type": "scoped_to",
                "confidence": "extracted",
                "id": f"concept-proj:{c.id}",
            })

    graph = {
        "version": "1.0",
        "workspace_id": workspace_id,
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "concept_count": len(concepts),
            "session_count": len(sessions),
            "project_count": len(projects),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph, indent=2, default=str), encoding="utf-8")

    return {"nodes": len(nodes), "edges": len(edges), "output_path": str(output_path)}
