"""Phase 3 tests — governance lint checks and service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from intelligent_chat.storage.models import (
    Base,
    Concept,
    GovernanceIssue,
    IngestSession,
    Project,
    Relationship,
    User,
    Workspace,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    user = User(email="test@example.com", name="Test")
    db.add(user)
    db.flush()
    workspace = Workspace(name="test", owner_id=user.id)
    db.add(workspace)
    db.flush()
    project = Project(workspace_id=workspace.id, name="myproject", visibility="workspace")
    db.add(project)
    db.commit()
    return engine, db, workspace.id, project.id


def make_concept(db: Session, workspace_id: int, title: str, **kwargs) -> Concept:
    c = Concept(
        workspace_id=workspace_id,
        title=title,
        type=kwargs.get("type", "concept"),
        description=kwargs.get("description", ""),
        body=kwargs.get("body", ""),
        confidence=kwargs.get("confidence", "extracted"),
        visibility=kwargs.get("visibility", "workspace"),
        created_at=kwargs.get("created_at", datetime.now(UTC).replace(tzinfo=None)),
        updated_at=kwargs.get("updated_at", datetime.now(UTC).replace(tzinfo=None)),
        resource=kwargs.get("resource"),
    )
    db.add(c)
    db.flush()
    return c


def make_relationship(db: Session, workspace_id: int, src_id: int, tgt_id: int, **kwargs) -> Relationship:
    r = Relationship(
        workspace_id=workspace_id,
        source_concept_id=src_id,
        target_concept_id=tgt_id,
        relation_type=kwargs.get("relation_type", "related_to"),
        confidence=kwargs.get("confidence", "extracted"),
        evidence_id=kwargs.get("evidence_id"),
        created_at=kwargs.get("created_at", datetime.now(UTC).replace(tzinfo=None)),
    )
    db.add(r)
    db.flush()
    return r


# ---------------------------------------------------------------------------
# Contradiction check
# ---------------------------------------------------------------------------

class TestContradictionCheck:
    def test_detects_contradicts_relationship(self):
        from intelligent_chat.governance.checks import check_contradiction

        _, db, workspace_id, _ = make_db()
        a = make_concept(db, workspace_id, "Concept A")
        b = make_concept(db, workspace_id, "Concept B")
        make_relationship(db, workspace_id, a.id, b.id, relation_type="contradicts")
        db.commit()

        issues = check_contradiction(db, workspace_id)
        assert len(issues) == 1
        assert issues[0].severity == "high"
        assert "Concept A" in issues[0].description

    def test_no_issue_for_non_contradicts(self):
        from intelligent_chat.governance.checks import check_contradiction

        _, db, workspace_id, _ = make_db()
        a = make_concept(db, workspace_id, "A")
        b = make_concept(db, workspace_id, "B")
        make_relationship(db, workspace_id, a.id, b.id, relation_type="uses")
        db.commit()

        assert check_contradiction(db, workspace_id) == []


# ---------------------------------------------------------------------------
# Orphan check
# ---------------------------------------------------------------------------

class TestOrphanCheck:
    def test_detects_old_concept_with_no_relationships(self):
        from intelligent_chat.governance.checks import check_orphan

        _, db, workspace_id, _ = make_db()
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
        make_concept(db, workspace_id, "Lonely Concept", created_at=old, updated_at=old)
        db.commit()

        issues = check_orphan(db, workspace_id, age_days=7)
        assert len(issues) == 1
        assert "Lonely Concept" in issues[0].description

    def test_no_issue_for_new_concept(self):
        from intelligent_chat.governance.checks import check_orphan

        _, db, workspace_id, _ = make_db()
        make_concept(db, workspace_id, "Brand New")
        db.commit()

        assert check_orphan(db, workspace_id, age_days=7) == []

    def test_no_issue_when_concept_has_relationship(self):
        from intelligent_chat.governance.checks import check_orphan

        _, db, workspace_id, _ = make_db()
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
        a = make_concept(db, workspace_id, "A", created_at=old, updated_at=old)
        b = make_concept(db, workspace_id, "B", created_at=old, updated_at=old)
        make_relationship(db, workspace_id, a.id, b.id)
        db.commit()

        assert check_orphan(db, workspace_id, age_days=7) == []


# ---------------------------------------------------------------------------
# Staleness check
# ---------------------------------------------------------------------------

class TestStalenessCheck:
    def test_detects_stale_concept_with_newer_session(self):
        from intelligent_chat.governance.checks import check_staleness

        _, db, workspace_id, project_id = make_db()
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=40)
        make_concept(db, workspace_id, "Old Concept", updated_at=old, project_id=project_id)

        sess = IngestSession(
            id="new-session-001",
            workspace_id=workspace_id,
            project_id=project_id,
            source_type="claude_code",
            status="normalized",
            started_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(sess)
        db.commit()

        issues = check_staleness(db, workspace_id, stale_days=30)
        assert len(issues) == 1
        assert "Old Concept" in issues[0].description

    def test_no_issue_when_no_newer_session(self):
        from intelligent_chat.governance.checks import check_staleness

        _, db, workspace_id, _ = make_db()
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=40)
        make_concept(db, workspace_id, "Old But Fine", updated_at=old)
        db.commit()

        assert check_staleness(db, workspace_id, stale_days=30) == []


# ---------------------------------------------------------------------------
# Broken link check
# ---------------------------------------------------------------------------

class TestBrokenLinkCheck:
    def test_detects_link_to_missing_concept(self):
        from intelligent_chat.governance.checks import check_broken_link

        _, db, workspace_id, _ = make_db()
        make_concept(db, workspace_id, "Real Concept",
                     body="See [Ghost Concept](ghost-concept.md) for more.")
        db.commit()

        issues = check_broken_link(db, workspace_id)
        assert len(issues) == 1
        assert "ghost-concept.md" in issues[0].description

    def test_no_issue_for_valid_link(self):
        from intelligent_chat.governance.checks import check_broken_link

        _, db, workspace_id, _ = make_db()
        make_concept(db, workspace_id, "Source",
                     body="See [Target Concept](target-concept.md) for details.")
        make_concept(db, workspace_id, "Target Concept")
        db.commit()

        assert check_broken_link(db, workspace_id) == []


# ---------------------------------------------------------------------------
# Coverage gap check
# ---------------------------------------------------------------------------

class TestCoverageGapCheck:
    def test_detects_normalized_session_with_no_concepts(self):
        from intelligent_chat.governance.checks import check_coverage_gap

        _, db, workspace_id, project_id = make_db()
        sess = IngestSession(
            id="empty-session-001",
            workspace_id=workspace_id,
            project_id=project_id,
            source_type="claude_code",
            status="normalized",
            started_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(sess)
        db.commit()

        issues = check_coverage_gap(db, workspace_id, lookback_days=30)
        assert len(issues) == 1
        assert "empty-session-001"[:12] in issues[0].description

    def test_no_issue_when_session_has_concepts(self):
        from intelligent_chat.governance.checks import check_coverage_gap

        _, db, workspace_id, project_id = make_db()
        sess = IngestSession(
            id="rich-session-001",
            workspace_id=workspace_id,
            project_id=project_id,
            source_type="claude_code",
            status="normalized",
            started_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(sess)
        db.flush()
        make_concept(db, workspace_id, "Something Learned",
                     resource="session:rich-session-001")
        db.commit()

        assert check_coverage_gap(db, workspace_id, lookback_days=30) == []


# ---------------------------------------------------------------------------
# Confidence drift check
# ---------------------------------------------------------------------------

class TestConfidenceDriftCheck:
    def test_detects_old_inferred_relationship_without_evidence(self):
        from intelligent_chat.governance.checks import check_confidence_drift

        _, db, workspace_id, _ = make_db()
        a = make_concept(db, workspace_id, "A")
        b = make_concept(db, workspace_id, "B")
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=20)
        make_relationship(db, workspace_id, a.id, b.id,
                          confidence="inferred", evidence_id=None, created_at=old)
        db.commit()

        issues = check_confidence_drift(db, workspace_id, drift_days=14)
        assert len(issues) == 1
        assert "inferred" in issues[0].description

    def test_no_issue_for_recent_inferred_relationship(self):
        from intelligent_chat.governance.checks import check_confidence_drift

        _, db, workspace_id, _ = make_db()
        a = make_concept(db, workspace_id, "A")
        b = make_concept(db, workspace_id, "B")
        make_relationship(db, workspace_id, a.id, b.id, confidence="inferred", evidence_id=None)
        db.commit()

        assert check_confidence_drift(db, workspace_id, drift_days=14) == []


# ---------------------------------------------------------------------------
# run_lint orchestrator
# ---------------------------------------------------------------------------

class TestRunLint:
    def test_run_lint_returns_summary(self):
        from intelligent_chat.governance.service import run_lint

        _, db, workspace_id, _ = make_db()
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
        make_concept(db, workspace_id, "Orphan", created_at=old, updated_at=old)
        db.commit()

        result = run_lint(db, workspace_id)
        assert result["total"] >= 1
        assert result["by_check"]["orphan"] >= 1

    def test_run_lint_persists_issues(self):
        from intelligent_chat.governance.service import run_lint

        _, db, workspace_id, _ = make_db()
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
        make_concept(db, workspace_id, "Orphan", created_at=old, updated_at=old)
        db.commit()

        run_lint(db, workspace_id)
        count = db.query(GovernanceIssue).filter_by(workspace_id=workspace_id).count()
        assert count >= 1

    def test_resolve_issue(self):
        from intelligent_chat.governance.service import resolve_issue, run_lint

        _, db, workspace_id, _ = make_db()
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
        make_concept(db, workspace_id, "Orphan", created_at=old, updated_at=old)
        db.commit()

        result = run_lint(db, workspace_id, checks=["orphan"])
        issue = result["issues"][0]

        resolved = resolve_issue(db, issue.id, workspace_id, note="Linked manually.")
        assert resolved.resolved is True
        assert resolved.resolution_note == "Linked manually."
