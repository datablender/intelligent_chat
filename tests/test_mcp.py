"""Tests for the MCP server tool functions."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from intelligent_chat.storage.models import Base, Concept, ConceptTag, User, Workspace

# ---------------------------------------------------------------------------
# Shared fixture — in-memory DB wired to the server's get_session
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def seeded_db(db_session):
    """Populate workspace + two concepts; return (session, workspace_id)."""
    user = User(email="u@x.com", name="U", role="admin")
    db_session.add(user)
    db_session.flush()
    ws = Workspace(name="ws", owner_id=user.id, visibility="private")
    db_session.add(ws)
    db_session.flush()

    c1 = Concept(
        workspace_id=ws.id, title="SQLAlchemy batch mode",
        description="Use batch_alter_table for SQLite migrations",
        type="pattern", confidence="extracted", visibility="workspace",
    )
    c2 = Concept(
        workspace_id=ws.id, title="FastAPI dependency injection",
        description="Annotated types carry Depends metadata",
        type="tool", confidence="extracted", visibility="workspace",
    )
    db_session.add_all([c1, c2])
    db_session.flush()
    db_session.add(ConceptTag(concept_id=c1.id, tag="alembic"))
    db_session.add(ConceptTag(concept_id=c1.id, tag="sqlite"))
    db_session.commit()
    return db_session, ws.id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_db(session):
    """Context manager that makes the MCP server's get_session return `session`."""
    return patch("intelligent_chat.storage.database.get_session", return_value=session)


# ---------------------------------------------------------------------------
# search_knowledge
# ---------------------------------------------------------------------------

class TestSearchKnowledge:
    def test_finds_matching_concept(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import search_knowledge
            result = search_knowledge(query="SQLAlchemy")

        assert "SQLAlchemy batch mode" in result
        assert "id:" in result

    def test_returns_no_results_message(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import search_knowledge
            result = search_knowledge(query="xyzzy_not_found")

        assert "No concepts found" in result

    def test_filters_by_type(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import search_knowledge
            result = search_knowledge(query="", concept_type="tool")

        assert "FastAPI dependency injection" in result
        assert "SQLAlchemy" not in result


# ---------------------------------------------------------------------------
# get_concept
# ---------------------------------------------------------------------------

class TestGetConcept:
    def test_returns_full_concept(self, seeded_db):
        session, ws_id = seeded_db
        concept = session.query(Concept).first()
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import get_concept
            result = get_concept(concept_id=concept.id)

        assert concept.title in result
        assert concept.type in result
        assert "alembic" in result  # tag

    def test_returns_not_found_for_missing_id(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import get_concept
            result = get_concept(concept_id=999999)

        assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# list_recent
# ---------------------------------------------------------------------------

class TestListRecent:
    def test_shows_recently_updated_concepts(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import list_recent
            result = list_recent(days=30)

        assert "SQLAlchemy batch mode" in result
        assert "FastAPI dependency injection" in result

    def test_empty_when_no_recent_concepts(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import list_recent
            result = list_recent(days=0)

        assert "No concepts" in result


# ---------------------------------------------------------------------------
# save_note
# ---------------------------------------------------------------------------

class TestSaveNote:
    def test_saves_concept_to_db(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import save_note
            result = save_note(
                title="Test insight",
                concept_type="insight",
                description="Something learned",
                tags=["testing"],
            )

        assert "Test insight" in result
        assert "id:" in result

        saved = session.query(Concept).filter_by(title="Test insight").first()
        assert saved is not None
        assert saved.workspace_id == ws_id
        assert saved.visibility == "workspace"
        assert any(t.tag == "testing" for t in saved.tags)

    def test_project_scope_sets_visibility(self, seeded_db):
        session, ws_id = seeded_db
        with (
            _patch_db(session),
            patch("intelligent_chat.mcp.server._workspace_id", ws_id),
        ):
            from intelligent_chat.mcp.server import save_note
            save_note(
                title="Project-specific note",
                concept_type="decision",
                description="Tied to this codebase",
                scope="project",
                project_id=42,
            )

        saved = session.query(Concept).filter_by(title="Project-specific note").first()
        assert saved.visibility == "project"
        assert saved.project_id == 42
