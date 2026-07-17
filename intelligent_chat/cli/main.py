import typer

from intelligent_chat.cli import export as export_cli
from intelligent_chat.cli import governance as governance_cli
from intelligent_chat.cli import ingest as ingest_cli
from intelligent_chat.cli import search as search_cli
from intelligent_chat.config import DEFAULT_WORKSPACE_ID

app = typer.Typer(name="ichat", help="Collective memory platform for AI-assisted work.")
app.add_typer(ingest_cli.app, name="ingest")
app.add_typer(search_cli.app, name="search")
app.add_typer(export_cli.app, name="export")
app.add_typer(governance_cli.app, name="governance")


@app.command("init")
def init(
    name: str = typer.Option("default", help="Workspace name"),
    email: str = typer.Option("user@example.com", help="Owner email"),
    display_name: str = typer.Option("Default User", "--display-name", help="Owner display name"),
) -> None:
    """Initialize the database and create a default workspace."""
    from intelligent_chat.storage.database import create_tables, get_session
    from intelligent_chat.storage.models import User, Workspace

    create_tables()
    db = get_session()
    try:
        existing = db.query(User).filter_by(email=email).first()
        if not existing:
            user = User(email=email, name=display_name, role="admin")
            db.add(user)
            db.flush()
            workspace = Workspace(name=name, owner_id=user.id, visibility="private")
            db.add(workspace)
            db.commit()
            typer.echo(f"Initialized: workspace '{name}' (id={workspace.id}), user '{email}'")
        else:
            typer.echo(f"Already initialized. Workspace owner: {existing.email}")
    finally:
        db.close()


@app.command("status")
def status() -> None:
    """Show summary of the knowledge base."""
    from intelligent_chat.storage.database import get_session
    from intelligent_chat.storage.models import Concept, IngestSession, Relationship

    db = get_session()
    try:
        sessions = db.query(IngestSession).count()
        normalized = db.query(IngestSession).filter_by(status="normalized").count()
        concepts = db.query(Concept).count()
        relationships = db.query(Relationship).count()
    finally:
        db.close()

    typer.echo(f"Sessions:      {sessions} total, {normalized} normalized")
    typer.echo(f"Concepts:      {concepts}")
    typer.echo(f"Relationships: {relationships}")


@app.command("mcp")
def mcp_serve() -> None:
    """Start the MCP server over stdio for Claude Code / AI agent integration."""
    from intelligent_chat.mcp.server import run
    run()


@app.command("embed")
def embed_concepts(
    workspace: int = typer.Option(DEFAULT_WORKSPACE_ID, help="Workspace ID"),
    force: bool = typer.Option(False, "--force", help="Regenerate embeddings even when they already exist"),
) -> None:
    """Generate semantic embeddings for all concepts (requires OPENAI_API_KEY)."""
    from intelligent_chat.embeddings.service import embed_all_concepts
    from intelligent_chat.storage.database import get_session

    db = get_session()
    try:
        typer.echo(f"Embedding concepts for workspace {workspace}{'  (force=true)' if force else ''}...")
        count = embed_all_concepts(db, workspace_id=workspace, force=force)
        typer.echo(f"Done. {count} concept(s) embedded.")
    finally:
        db.close()


@app.command("api")
def api_serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on file changes (dev mode)"),
) -> None:
    """Start the REST API server (FastAPI + uvicorn)."""
    import uvicorn
    uvicorn.run(
        "intelligent_chat.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
