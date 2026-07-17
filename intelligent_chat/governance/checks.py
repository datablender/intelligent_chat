"""Governance lint checks — each returns a list of GovernanceIssue instances to persist."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from intelligent_chat.storage.models import (
    Concept,
    GovernanceIssue,
    IngestSession,
    Relationship,
)

# Thresholds (overridable via function args for testing)
ORPHAN_AGE_DAYS = 7
STALENESS_DAYS = 30
COVERAGE_LOOKBACK_DAYS = 30
CONFIDENCE_DRIFT_DAYS = 14

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")


def _safe_filename(title: str) -> str:
    name = title.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    return name[:80] + ".md"


def _issue(
    workspace_id: int,
    issue_type: str,
    severity: str,
    description: str,
    entity_id: int | None = None,
    entity_type: str | None = None,
) -> GovernanceIssue:
    return GovernanceIssue(
        workspace_id=workspace_id,
        issue_type=issue_type,
        severity=severity,
        affected_entity_id=entity_id,
        affected_entity_type=entity_type,
        description=description,
    )


# ---------------------------------------------------------------------------
# 1. Contradiction
# ---------------------------------------------------------------------------

def check_contradiction(db: Session, workspace_id: int) -> list[GovernanceIssue]:
    """Flag concept pairs linked by a 'contradicts' relationship for human review."""
    rels = (
        db.query(Relationship)
        .filter_by(workspace_id=workspace_id, relation_type="contradicts")
        .all()
    )
    issues = []
    for rel in rels:
        src = db.get(Concept, rel.source_concept_id)
        tgt = db.get(Concept, rel.target_concept_id)
        if src and tgt:
            issues.append(_issue(
                workspace_id,
                issue_type="contradiction",
                severity="high",
                description=(
                    f"Concepts '{src.title}' and '{tgt.title}' are marked as contradicting "
                    f"each other (relationship id={rel.id}). Review and resolve."
                ),
                entity_id=rel.id,
                entity_type="relationship",
            ))
    return issues


# ---------------------------------------------------------------------------
# 2. Orphan
# ---------------------------------------------------------------------------

def check_orphan(
    db: Session,
    workspace_id: int,
    age_days: int = ORPHAN_AGE_DAYS,
) -> list[GovernanceIssue]:
    """Flag concepts older than age_days with no incoming or outgoing relationships."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=age_days)

    has_rel = exists().where(
        or_(
            Relationship.source_concept_id == Concept.id,
            Relationship.target_concept_id == Concept.id,
        )
    )
    orphans = (
        db.query(Concept)
        .filter(
            Concept.workspace_id == workspace_id,
            Concept.created_at < cutoff,
            ~has_rel,
        )
        .all()
    )
    return [
        _issue(
            workspace_id,
            issue_type="orphan",
            severity="medium",
            description=(
                f"Concept '{c.title}' (id={c.id}) has no relationships and was created "
                f"{age_days}+ days ago. Consider linking it or removing it."
            ),
            entity_id=c.id,
            entity_type="concept",
        )
        for c in orphans
    ]


# ---------------------------------------------------------------------------
# 3. Staleness
# ---------------------------------------------------------------------------

def check_staleness(
    db: Session,
    workspace_id: int,
    stale_days: int = STALENESS_DAYS,
) -> list[GovernanceIssue]:
    """Flag concepts not updated in stale_days while newer sessions exist in their project."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=stale_days)

    stale_concepts = (
        db.query(Concept)
        .filter(
            Concept.workspace_id == workspace_id,
            Concept.updated_at < cutoff,
        )
        .all()
    )

    issues = []
    for concept in stale_concepts:
        # Check if a new session exists in the same project (or any project for workspace concepts)
        q = db.query(IngestSession).filter(
            IngestSession.workspace_id == workspace_id,
            IngestSession.started_at > concept.updated_at,
        )
        if concept.project_id:
            q = q.filter(IngestSession.project_id == concept.project_id)

        has_newer = q.first() is not None
        if has_newer:
            issues.append(_issue(
                workspace_id,
                issue_type="staleness",
                severity="low",
                description=(
                    f"Concept '{concept.title}' (id={concept.id}) has not been updated in "
                    f"{stale_days}+ days but newer sessions have been ingested since then. "
                    "Consider re-normalizing or manually updating this concept."
                ),
                entity_id=concept.id,
                entity_type="concept",
            ))
    return issues


# ---------------------------------------------------------------------------
# 4. Broken link
# ---------------------------------------------------------------------------

def check_broken_link(db: Session, workspace_id: int) -> list[GovernanceIssue]:
    """Flag markdown links in concept bodies pointing to non-existent concept filenames."""
    concepts = db.query(Concept).filter_by(workspace_id=workspace_id).all()
    known_files = {_safe_filename(c.title) for c in concepts}

    issues = []
    for concept in concepts:
        body = concept.body or ""
        for match in _LINK_RE.finditer(body):
            target_file = match.group(2)
            if target_file not in known_files:
                issues.append(_issue(
                    workspace_id,
                    issue_type="broken_link",
                    severity="medium",
                    description=(
                        f"Concept '{concept.title}' (id={concept.id}) contains a link to "
                        f"'{target_file}' which does not match any known concept. "
                        "The target concept may have been renamed or deleted."
                    ),
                    entity_id=concept.id,
                    entity_type="concept",
                ))
    return issues


# ---------------------------------------------------------------------------
# 5. Coverage gap
# ---------------------------------------------------------------------------

def check_coverage_gap(
    db: Session,
    workspace_id: int,
    lookback_days: int = COVERAGE_LOOKBACK_DAYS,
) -> list[GovernanceIssue]:
    """Flag sessions that were normalized but produced zero concepts."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=lookback_days)

    recent_sessions = (
        db.query(IngestSession)
        .filter(
            IngestSession.workspace_id == workspace_id,
            IngestSession.status == "normalized",
            IngestSession.started_at >= cutoff,
        )
        .all()
    )

    issues = []
    for sess in recent_sessions:
        concept_count = (
            db.query(Concept)
            .filter(
                Concept.workspace_id == workspace_id,
                Concept.resource == f"session:{sess.id}",
            )
            .count()
        )
        if concept_count == 0:
            started = sess.started_at.strftime("%Y-%m-%d") if sess.started_at else "unknown"
            issues.append(_issue(
                workspace_id,
                issue_type="coverage_gap",
                severity="medium",
                description=(
                    f"Session {sess.id[:12]}... ({sess.source_type}, started {started}) "
                    "was normalized but produced zero concept pages. "
                    "Consider re-processing with `ichat ingest reprocess`."
                ),
                entity_id=None,
                entity_type="session",
            ))
    return issues


# ---------------------------------------------------------------------------
# 6. Confidence drift
# ---------------------------------------------------------------------------

def check_confidence_drift(
    db: Session,
    workspace_id: int,
    drift_days: int = CONFIDENCE_DRIFT_DAYS,
) -> list[GovernanceIssue]:
    """Flag inferred relationships with no evidence that haven't been reinforced recently."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=drift_days)

    drifting = (
        db.query(Relationship)
        .filter(
            Relationship.workspace_id == workspace_id,
            Relationship.confidence == "inferred",
            Relationship.evidence_id.is_(None),
            Relationship.created_at < cutoff,
        )
        .all()
    )

    issues = []
    for rel in drifting:
        src = db.get(Concept, rel.source_concept_id)
        tgt = db.get(Concept, rel.target_concept_id)
        src_title = src.title if src else f"concept:{rel.source_concept_id}"
        tgt_title = tgt.title if tgt else f"concept:{rel.target_concept_id}"
        issues.append(_issue(
            workspace_id,
            issue_type="confidence_drift",
            severity="low",
            description=(
                f"Relationship '{src_title}' → '{tgt_title}' (type={rel.relation_type}) "
                f"is inferred with no evidence and has not been reinforced in {drift_days}+ days. "
                "Consider verifying or removing this relationship."
            ),
            entity_id=rel.id,
            entity_type="relationship",
        ))
    return issues
