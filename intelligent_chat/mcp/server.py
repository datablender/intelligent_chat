"""MCP server — exposes the iChat knowledge base as tools for Claude Code and other AI agents."""

from __future__ import annotations

from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

from intelligent_chat.config import DEFAULT_WORKSPACE_ID

mcp_server = FastMCP(
    "ichat-memory",
    instructions=(
        "This server gives you access to a collective memory knowledge base built from past AI "
        "coding sessions. Search it before tackling a problem — a teammate (or past you) may have "
        "already solved it. Use save_note to preserve valuable discoveries during this session."
    ),
)

_workspace_id = DEFAULT_WORKSPACE_ID


@mcp_server.tool()
def search_knowledge(
    query: str,
    concept_type: str | None = None,
    tag: str | None = None,
    limit: int = 10,
) -> str:
    """Search the collective memory knowledge base for concepts from past AI sessions.

    Returns ranked concept summaries with IDs. Use get_concept(id) to read the full body.

    concept_type options: decision, pattern, tool, error, architecture, insight, file, dependency
    """
    from intelligent_chat.search.service import search_concepts
    from intelligent_chat.storage.database import get_session

    db = get_session()
    try:
        results = search_concepts(
            db,
            workspace_id=_workspace_id,
            query=query,
            concept_type=concept_type,
            tag=tag,
            limit=min(limit, 20),
        )
    finally:
        db.close()

    if not results:
        return "No concepts found. Try different keywords or run `ichat embed` then use semantic_search."

    lines = [f"Found {len(results)} concept(s) matching '{query}':\n"]
    for r in results:
        tags_str = f"\n  tags: {', '.join(r.tags)}" if r.tags else ""
        proj_str = f"  [project:{r.project_id}]" if r.project_id else ""
        lines.append(
            f"[id:{r.id}] [{r.type}] {r.title}{proj_str}\n"
            f"  {r.description or '(no description)'}{tags_str}"
        )
    return "\n\n".join(lines)


@mcp_server.tool()
def semantic_search(query: str, limit: int = 10, min_score: float = 0.5) -> str:
    """Search the knowledge base by semantic similarity rather than keyword matching.

    Requires OPENAI_API_KEY to be set and concepts to have been embedded via `ichat embed`.
    Useful when you know what you're looking for conceptually but don't know the exact terms.
    """
    from intelligent_chat.search.service import search_concepts_semantic
    from intelligent_chat.storage.database import get_session

    db = get_session()
    try:
        results = search_concepts_semantic(
            db,
            workspace_id=_workspace_id,
            query=query,
            limit=min(limit, 20),
            min_score=min_score,
        )
    finally:
        db.close()

    if not results:
        return (
            "No concepts found above the similarity threshold. "
            "Try lowering min_score or run `ichat embed` first."
        )

    lines = [f"Found {len(results)} concept(s) (semantic):\n"]
    for r in results:
        proj_str = f"  [project:{r.project_id}]" if r.project_id else ""
        lines.append(
            f"[id:{r.id}] [{r.type}] {r.title}{proj_str}  ({r.score}% match)\n"
            f"  {r.description or '(no description)'}"
        )
    return "\n\n".join(lines)


@mcp_server.tool()
def get_concept(concept_id: int) -> str:
    """Fetch the full body and metadata of a concept by its ID (returned by search_knowledge).

    Returns the complete concept page including body, tags, confidence, source session, and timestamps.
    """
    from intelligent_chat.storage.database import get_session
    from intelligent_chat.storage.models import Concept

    db = get_session()
    try:
        concept = db.get(Concept, concept_id)
        if not concept or concept.workspace_id != _workspace_id:
            return f"Concept {concept_id} not found."

        tags_str = ", ".join(t.tag for t in concept.tags) if concept.tags else "none"
        updated = concept.updated_at.isoformat() if concept.updated_at else "unknown"

        header = (
            f"# {concept.title}\n\n"
            f"**Type:** {concept.type}  |  **Confidence:** {concept.confidence}  |  "
            f"**Visibility:** {concept.visibility}\n"
            f"**Tags:** {tags_str}\n"
            f"**Source:** {concept.resource or 'unknown'}  |  **Updated:** {updated}\n"
        )
        if concept.description:
            header += f"\n**Summary:** {concept.description}\n"

        body = f"\n---\n\n{concept.body}" if concept.body else ""
        return header + body
    finally:
        db.close()


@mcp_server.tool()
def list_recent(days: int = 7, limit: int = 20) -> str:
    """List concepts added or updated in the last N days.

    Useful for catching up on what the team has learned recently before starting a new task.
    """
    from sqlalchemy import desc

    from intelligent_chat.storage.database import get_session
    from intelligent_chat.storage.models import Concept

    db = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        concepts = (
            db.query(Concept)
            .filter(
                Concept.workspace_id == _workspace_id,
                Concept.updated_at >= cutoff,
            )
            .order_by(desc(Concept.updated_at))
            .limit(limit)
            .all()
        )
    finally:
        db.close()

    if not concepts:
        return f"No concepts updated in the past {days} day(s)."

    lines = [f"{len(concepts)} concept(s) updated in the past {days} day(s):\n"]
    for c in concepts:
        updated = c.updated_at.strftime("%Y-%m-%d") if c.updated_at else "unknown"
        lines.append(f"[id:{c.id}] [{c.type}] {c.title}  ({updated})")
    return "\n".join(lines)


@mcp_server.tool()
def save_note(
    title: str,
    concept_type: str,
    description: str,
    body: str | None = None,
    tags: list[str] | None = None,
    scope: str = "workspace",
    project_id: int | None = None,
) -> str:
    """Save an insight, decision, or pattern to the knowledge base during this session.

    Use this to preserve valuable discoveries so they benefit future sessions and teammates.

    concept_type: decision | pattern | tool | error | architecture | insight
    scope: workspace (reusable across all projects) | project (tied to this codebase)
    project_id: required when scope=project
    """
    from intelligent_chat.storage.database import get_session
    from intelligent_chat.storage.models import Concept, ConceptTag

    db = get_session()
    try:
        concept = Concept(
            workspace_id=_workspace_id,
            project_id=int(project_id) if project_id and scope == "project" else None,
            title=title,
            type=concept_type,
            description=description,
            body=body,
            confidence="extracted",
            visibility="project" if scope == "project" else "workspace",
            resource="mcp:save_note",
        )
        db.add(concept)
        db.flush()
        for tag in (tags or []):
            db.add(ConceptTag(concept_id=concept.id, tag=tag.strip()))
        db.commit()
        return f"Saved concept [id:{concept.id}]: {title}\nScope: {scope}  Type: {concept_type}"
    finally:
        db.close()


def run() -> None:
    """Start the MCP server over stdio (called by `ichat mcp`)."""
    mcp_server.run()
