"""CLI commands for exporting the knowledge base."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from intelligent_chat.config import DEFAULT_WORKSPACE_ID
from intelligent_chat.storage.database import get_session

app = typer.Typer(help="Export the knowledge base to OKF or graph formats.")


@app.command("okf")
def export_okf(
    output: Annotated[Path, typer.Option("--output", "-o", help="Output directory for the OKF bundle")] = Path("./knowledge-base"),
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Export all accessible concepts as an OKF markdown bundle.

    Produces one .md file per concept, plus index.md and an appended log.md.
    Compatible with Graphify, Obsidian, and any markdown-aware tool.
    """
    from intelligent_chat.export.okf import export_okf as _export

    db = get_session()
    try:
        result = _export(db, workspace_id=workspace, output_dir=output)
    finally:
        db.close()

    typer.echo(f"Exported {result['exported']} concepts → {result['output_dir']}")


@app.command("graph")
def export_graph(
    output: Annotated[Path, typer.Option("--output", "-o", help="Output path for graph.json")] = Path("./graphify-out/graph.json"),
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Export the knowledge graph as a Graphify-compatible graph.json file.

    Run `graphify serve <output>` to visualise and expose via MCP.
    """
    from intelligent_chat.export.graph import export_graph as _export

    db = get_session()
    try:
        result = _export(db, workspace_id=workspace, output_path=output)
    finally:
        db.close()

    typer.echo(
        f"Graph exported: {result['nodes']} nodes, {result['edges']} edges → {result['output_path']}"
    )
