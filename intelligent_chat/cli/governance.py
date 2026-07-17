"""CLI commands for knowledge base governance and lint."""

from __future__ import annotations

from typing import Annotated

import typer

from intelligent_chat.config import DEFAULT_WORKSPACE_ID
from intelligent_chat.storage.database import get_session

app = typer.Typer(help="Governance lint checks for the knowledge base.")

_SEVERITY_COLORS = {"high": "red", "medium": "yellow", "low": "bright_black"}


@app.command("lint")
def lint(
    check: Annotated[list[str] | None, typer.Option(
        "--check",
        help="Run specific check(s): contradiction orphan staleness broken_link coverage_gap confidence_drift",
    )] = None,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Run governance lint checks and surface issues.

    By default runs all 6 checks. Pass --check <name> one or more times to run a subset.
    New issues are written to the database. Already-open identical issues are NOT deduplicated
    automatically — use `governance issues` to review and `governance resolve` to close them.
    """
    from intelligent_chat.governance.service import run_lint

    db = get_session()
    try:
        result = run_lint(db, workspace_id=workspace, checks=list(check) if check else None)
    finally:
        db.close()

    total = result["total"]
    if total == 0:
        typer.echo("All checks passed — no new issues found.")
        return

    typer.echo(f"\n{total} new issue(s) found:\n")
    by_sev = result["by_severity"]
    if by_sev.get("high"):
        typer.secho(f"  HIGH   : {by_sev['high']}", fg="red", bold=True)
    if by_sev.get("medium"):
        typer.secho(f"  MEDIUM : {by_sev['medium']}", fg="yellow")
    if by_sev.get("low"):
        typer.secho(f"  LOW    : {by_sev['low']}", fg="bright_black")

    typer.echo("\nBy check:")
    for name, count in result["by_check"].items():
        if count:
            typer.echo(f"  {name:<20} {count}")

    typer.echo("\nRun `ichat governance issues` to see details.")


@app.command("issues")
def issues(
    resolved: Annotated[bool, typer.Option("--resolved", help="Show resolved issues instead of open ones")] = False,
    severity: Annotated[str | None, typer.Option("--severity", help="Filter by severity: high | medium | low")] = None,
    issue_type: Annotated[str | None, typer.Option("--type", help="Filter by check type")] = None,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """List governance issues (open by default)."""
    from intelligent_chat.governance.service import list_issues

    db = get_session()
    try:
        found = list_issues(
            db,
            workspace_id=workspace,
            resolved=resolved,
            severity=severity,
            issue_type=issue_type,
        )
    finally:
        db.close()

    label = "resolved" if resolved else "open"
    if not found:
        typer.echo(f"No {label} issues.")
        return

    typer.echo(f"{len(found)} {label} issue(s):\n")
    for issue in found:
        color = _SEVERITY_COLORS.get(issue.severity, "white")
        header = f"  #{issue.id}  [{issue.severity.upper()}]  {issue.issue_type}"
        typer.secho(header, fg=color, bold=(issue.severity == "high"))
        typer.echo(f"  {issue.description}")
        if issue.resolution_note:
            typer.echo(f"  Resolution: {issue.resolution_note}")
        typer.echo()


@app.command("resolve")
def resolve(
    issue_id: Annotated[int, typer.Argument(help="Issue ID to resolve")],
    note: Annotated[str | None, typer.Option("--note", "-n", help="Optional resolution note")] = None,
    workspace: Annotated[int, typer.Option()] = DEFAULT_WORKSPACE_ID,
) -> None:
    """Mark a governance issue as resolved."""
    from intelligent_chat.governance.service import resolve_issue

    db = get_session()
    try:
        issue = resolve_issue(db, issue_id=issue_id, workspace_id=workspace, note=note)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    finally:
        db.close()

    typer.echo(f"Issue #{issue.id} ({issue.issue_type}) marked as resolved.")
    if note:
        typer.echo(f"Note: {note}")
