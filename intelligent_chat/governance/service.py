"""Governance service — orchestrates lint checks and persists findings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from intelligent_chat.governance.checks import (
    check_broken_link,
    check_confidence_drift,
    check_contradiction,
    check_coverage_gap,
    check_orphan,
    check_staleness,
)
from intelligent_chat.storage.models import GovernanceIssue


def run_lint(
    db: Session,
    workspace_id: int,
    *,
    checks: list[str] | None = None,
) -> dict:
    """Run all (or a subset of) governance lint checks and persist new issues.

    checks: list of check names to run; None means run all.
    Returns a summary dict: {total: int, by_check: dict, by_severity: dict}
    """
    all_checks = {
        "contradiction": check_contradiction,
        "orphan": check_orphan,
        "staleness": check_staleness,
        "broken_link": check_broken_link,
        "coverage_gap": check_coverage_gap,
        "confidence_drift": check_confidence_drift,
    }

    if checks:
        run = {k: v for k, v in all_checks.items() if k in checks}
    else:
        run = all_checks

    new_issues: list[GovernanceIssue] = []
    by_check: dict[str, int] = {}

    for name, fn in run.items():
        found = fn(db, workspace_id)
        by_check[name] = len(found)
        new_issues.extend(found)

    for issue in new_issues:
        db.add(issue)
    db.commit()

    by_severity: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for issue in new_issues:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1

    return {
        "total": len(new_issues),
        "by_check": by_check,
        "by_severity": by_severity,
        "issues": new_issues,
    }


def list_issues(
    db: Session,
    workspace_id: int,
    *,
    resolved: bool = False,
    severity: str | None = None,
    issue_type: str | None = None,
) -> list[GovernanceIssue]:
    """Return open (or resolved) governance issues, optionally filtered."""
    q = (
        db.query(GovernanceIssue)
        .filter_by(workspace_id=workspace_id, resolved=resolved)
    )
    if severity:
        q = q.filter(GovernanceIssue.severity == severity)
    if issue_type:
        q = q.filter(GovernanceIssue.issue_type == issue_type)

    # High → medium → low; newest first within each severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues = q.all()
    issues.sort(key=lambda i: (severity_order.get(i.severity, 9), -i.id))
    return issues


def resolve_issue(
    db: Session,
    issue_id: int,
    workspace_id: int,
    note: str | None = None,
) -> GovernanceIssue:
    """Mark a governance issue as resolved."""
    issue = db.get(GovernanceIssue, issue_id)
    if not issue:
        raise ValueError(f"Governance issue {issue_id} not found.")
    if issue.workspace_id != workspace_id:
        raise ValueError(f"Issue {issue_id} does not belong to workspace {workspace_id}.")
    issue.resolved = True
    issue.resolution_note = note
    db.commit()
    return issue
