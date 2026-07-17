"""CLI commands for ingesting AI coding sessions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from intelligent_chat.config import DEFAULT_WORKSPACE_ID
from intelligent_chat.storage.database import get_session

app = typer.Typer(help="Ingest AI coding sessions into the knowledge base.")


@app.command("list-projects")
def list_projects() -> None:
    """List all Claude Code projects with their session counts."""
    from intelligent_chat.ingestion.claude_code import list_projects as _list

    projects = _list()
    if not projects:
        typer.echo("No Claude Code projects found.")
        return
    typer.echo(f"{'Sessions':>8}  Project slug")
    typer.echo("-" * 60)
    for p in projects:
        typer.echo(f"{p['sessions']:>8}  {p['slug']}")


@app.command("scan")
def scan(
    source: Annotated[str, typer.Option(help="Source type: claude_code | copilot")] = "claude_code",
    project: Annotated[str | None, typer.Option(
        help="Filter to a specific project — accepts a slug, partial name, or real path. "
             "Run `ichat ingest list-projects` to see available slugs."
    )] = None,
    no_normalize: Annotated[bool, typer.Option("--no-normalize", help="Skip LLM normalization")] = False,
    workspace: Annotated[int, typer.Option(help="Workspace ID")] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Scan source directories and ingest all new sessions."""
    from intelligent_chat.ingestion.service import scan_and_ingest

    label = f"project '{project}'" if project else "all projects"
    typer.echo(f"Scanning {source} sessions ({label})...")
    db = get_session()
    try:
        results = scan_and_ingest(
            db,
            workspace_id=workspace,
            normalize=not no_normalize,
            source=source,
            project=project,
        )
    finally:
        db.close()

    new = [r for r in results if not r.get("skipped")]
    skipped = [r for r in results if r.get("skipped")]
    typer.echo(f"  {len(new)} new sessions ingested, {len(skipped)} already present")
    for r in new:
        status = r.get("status", "ingested")
        concepts = r.get("concepts_created", 0)
        typer.echo(f"  ✓ {r['session_id'][:8]}... [{status}] +{concepts} concepts")


@app.command("file")
def ingest_file(
    path: Annotated[Path, typer.Argument(help="Path to a JSONL or markdown file")],
    no_normalize: Annotated[bool, typer.Option("--no-normalize")] = False,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Ingest a specific file by path."""
    from intelligent_chat.ingestion import claude_code, copilot
    from intelligent_chat.ingestion.service import ingest_envelope

    if not path.exists():
        typer.echo(f"File not found: {path}", err=True)
        raise typer.Exit(1)

    if path.suffix == ".jsonl":
        envelope = claude_code.parse_session_file(path)
    elif path.suffix == ".md":
        envelope = copilot.parse_copilot_file(path)
    else:
        typer.echo(f"Unsupported file type: {path.suffix}", err=True)
        raise typer.Exit(1)

    if not envelope:
        typer.echo("No messages found in file — nothing to ingest.", err=True)
        raise typer.Exit(1)

    db = get_session()
    try:
        result = ingest_envelope(envelope, db, workspace_id=workspace, normalize=not no_normalize)
    finally:
        db.close()

    typer.echo(f"Session {result['session_id']}: {result['status']}")


@app.command("session")
def ingest_session(
    session_id: Annotated[str, typer.Argument(help="Claude Code session UUID")],
    no_normalize: Annotated[bool, typer.Option("--no-normalize")] = False,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Ingest a specific session by its UUID."""
    from intelligent_chat.ingestion import claude_code
    from intelligent_chat.ingestion.service import ingest_envelope

    envelope = claude_code.get_session(session_id)
    if not envelope:
        typer.echo(f"Session {session_id} not found in Claude Code directory.", err=True)
        raise typer.Exit(1)

    db = get_session()
    try:
        result = ingest_envelope(envelope, db, workspace_id=workspace, normalize=not no_normalize)
    finally:
        db.close()

    typer.echo(f"Session {result['session_id']}: {result['status']}")


@app.command("reprocess")
def reprocess(
    session_id: Annotated[str, typer.Argument(help="Session UUID to re-normalize")],
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Re-run LLM normalization for a session using its raw archive."""
    from intelligent_chat.ingestion.service import reprocess_session

    db = get_session()
    try:
        result = reprocess_session(session_id, db, workspace_id=workspace)
    finally:
        db.close()

    typer.echo(
        f"Reprocessed {session_id}: "
        f"+{result['concepts_created']} created, "
        f"~{result['concepts_updated']} updated, "
        f"+{result['relationships_created']} relationships"
    )


@app.command("hook-trigger")
def hook_trigger(
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Handle a Claude Code pre-compaction hook event from stdin (called by Claude Code automatically)."""
    from intelligent_chat.ingestion import claude_code
    from intelligent_chat.ingestion.service import ingest_envelope

    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    session_id = payload.get("session_id") or payload.get("sessionId")
    if not session_id:
        sys.exit(0)

    envelope = claude_code.get_session(session_id)
    if not envelope:
        sys.exit(0)

    db = get_session()
    try:
        ingest_envelope(envelope, db, workspace_id=workspace, normalize=True)
    finally:
        db.close()


@app.command("hook")
def hook(
    action: Annotated[str, typer.Argument(help="install | uninstall")],
) -> None:
    """Install or uninstall the Claude Code pre-compaction hook."""
    settings_path = Path.home() / ".claude" / "settings.json"

    if settings_path.exists():
        with settings_path.open() as f:
            settings = json.load(f)
    else:
        settings = {}

    hook_command = "ichat ingest hook-trigger"

    if action == "install":
        hooks = settings.setdefault("hooks", {})
        pre_compact = hooks.setdefault("PreCompact", [])

        # Check not already installed
        for entry in pre_compact:
            for h in entry.get("hooks", []):
                if h.get("command") == hook_command:
                    typer.echo("Hook already installed.")
                    return

        pre_compact.append({
            "matcher": "",
            "hooks": [{"type": "command", "command": hook_command}],
        })
        with settings_path.open("w") as f:
            json.dump(settings, f, indent=2)
        typer.echo(f"Hook installed in {settings_path}")

    elif action == "uninstall":
        hooks = settings.get("hooks", {})
        pre_compact = hooks.get("PreCompact", [])
        hooks["PreCompact"] = [
            entry for entry in pre_compact
            if not any(h.get("command") == hook_command for h in entry.get("hooks", []))
        ]
        with settings_path.open("w") as f:
            json.dump(settings, f, indent=2)
        typer.echo("Hook removed.")

    else:
        typer.echo(f"Unknown action: {action}. Use install or uninstall.", err=True)
        raise typer.Exit(1)
