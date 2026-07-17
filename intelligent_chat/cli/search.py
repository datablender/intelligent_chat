"""CLI commands for searching the knowledge base."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import typer

from intelligent_chat.config import DEFAULT_WORKSPACE_ID
from intelligent_chat.storage.database import get_session

app = typer.Typer(help="Search the knowledge base.")


@app.command("query")
def query(
    text: Annotated[str, typer.Argument(help="Search text")],
    concept_type: Annotated[str | None, typer.Option("--type", help="Filter by concept type (decision, tool, pattern, ...)")] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Filter by tag")] = None,
    project_id: Annotated[int | None, typer.Option("--project-id", help="Filter to a specific project ID")] = None,
    from_date: Annotated[str | None, typer.Option("--from", help="Updated after this date (YYYY-MM-DD)")] = None,
    to_date: Annotated[str | None, typer.Option("--to", help="Updated before this date (YYYY-MM-DD)")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results")] = 20,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Search concepts by text with optional filters."""
    from intelligent_chat.search.service import search_concepts

    from_dt = datetime.fromisoformat(from_date) if from_date else None
    to_dt = datetime.fromisoformat(to_date) if to_date else None

    db = get_session()
    try:
        results = search_concepts(
            db,
            workspace_id=workspace,
            query=text,
            concept_type=concept_type,
            tag=tag,
            project_id=project_id,
            from_date=from_dt,
            to_date=to_dt,
            limit=limit,
        )
    finally:
        db.close()

    if not results:
        typer.echo("No results found.")
        return

    typer.echo(f"{len(results)} result(s) for '{text}':\n")
    for r in results:
        project_label = f" [project:{r.project_id}]" if r.project_id else ""
        tags_label = f"  tags: {', '.join(r.tags)}" if r.tags else ""
        typer.echo(f"  [{r.type}] {r.title}{project_label}")
        if r.description:
            typer.echo(f"  {r.description}")
        if tags_label:
            typer.echo(tags_label)
        typer.echo(f"  confidence: {r.confidence}  source: {r.source_session or 'unknown'}")
        typer.echo()


@app.command("semantic")
def semantic(
    text: Annotated[str, typer.Argument(help="Natural-language query")],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    min_score: Annotated[float, typer.Option("--min-score", help="Minimum cosine similarity (0–1)")] = 0.5,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Search concepts by semantic similarity (requires OPENAI_API_KEY + ichat embed)."""
    from intelligent_chat.search.service import search_concepts_semantic

    db = get_session()
    try:
        results = search_concepts_semantic(
            db, workspace_id=workspace, query=text, limit=limit, min_score=min_score,
        )
    finally:
        db.close()

    if not results:
        typer.echo("No results. Lower --min-score or run `ichat embed` first.")
        return

    typer.echo(f"{len(results)} result(s) for '{text}' (semantic):\n")
    for r in results:
        project_label = f" [project:{r.project_id}]" if r.project_id else ""
        typer.echo(f"  [{r.type}] {r.title}{project_label}  ({r.score}% match)")
        if r.description:
            typer.echo(f"  {r.description}")
        typer.echo()


@app.command("sessions")
def sessions(
    text: Annotated[str, typer.Argument(help="Search text to find in message content")],
    limit: Annotated[int, typer.Option("--limit")] = 10,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Search session message content and list matching sessions."""
    from intelligent_chat.search.service import search_sessions

    db = get_session()
    try:
        results = search_sessions(db, workspace_id=workspace, query=text, limit=limit)
    finally:
        db.close()

    if not results:
        typer.echo("No sessions found.")
        return

    typer.echo(f"{len(results)} session(s) matching '{text}':\n")
    for s in results:
        started = s["started_at"] or "unknown"
        typer.echo(f"  {s['session_id'][:12]}...  [{s['source_type']}]  started: {started}")
        typer.echo(f"  ...{s['snippet']}...")
        typer.echo()


@app.command("session")
def session_concepts(
    session_id: Annotated[str, typer.Argument(help="Session UUID")],
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Show all concepts extracted from a specific session."""
    from intelligent_chat.search.service import get_session_concepts

    db = get_session()
    try:
        results = get_session_concepts(db, workspace_id=workspace, session_id=session_id)
    finally:
        db.close()

    if not results:
        typer.echo(f"No concepts found for session {session_id}.")
        return

    typer.echo(f"{len(results)} concept(s) from session {session_id}:\n")
    for r in results:
        typer.echo(f"  [{r.type}] {r.title}  ({r.confidence})")
        if r.description:
            typer.echo(f"  {r.description}")
        typer.echo()
