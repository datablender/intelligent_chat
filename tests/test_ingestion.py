"""Phase 1 tests — connectors, archive writer, and normalization pipeline (mocked LLM)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from intelligent_chat.storage.models import (
    Base,
    Concept,
    IngestSession,
    Message,
    Relationship,
    User,
    Workspace,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db() -> tuple:
    """Return (engine, session) backed by in-memory SQLite."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    user = User(email="test@example.com", name="Test")
    db.add(user)
    db.flush()
    workspace = Workspace(name="test", owner_id=user.id)
    db.add(workspace)
    db.commit()
    return engine, db, workspace.id


# ---------------------------------------------------------------------------
# Claude Code connector
# ---------------------------------------------------------------------------

class TestClaudeCodeConnector:
    def test_parse_valid_session(self):
        from intelligent_chat.ingestion.claude_code import parse_session_file

        result = parse_session_file(FIXTURES / "sample_session.jsonl")

        assert result is not None
        assert result["session_id"] == "sample_session"
        assert result["source_type"] == "claude_code"
        assert result["project_name"] == "myproject"
        assert len(result["messages"]) == 4
        assert result["started_at"] is not None
        assert result["ended_at"] > result["started_at"]
        assert result["token_count"] == 83  # 48 + 35 output tokens

    def test_parse_message_roles(self):
        from intelligent_chat.ingestion.claude_code import parse_session_file

        result = parse_session_file(FIXTURES / "sample_session.jsonl")
        roles = [m["role"] for m in result["messages"]]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_parse_empty_file_returns_none(self, tmp_path):
        from intelligent_chat.ingestion.claude_code import parse_session_file

        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        assert parse_session_file(empty) is None

    def test_parse_file_with_only_queue_ops_returns_none(self, tmp_path):
        from intelligent_chat.ingestion.claude_code import parse_session_file

        ops_only = tmp_path / "ops.jsonl"
        ops_only.write_text(
            '{"type":"queue-operation","operation":"enqueue","sessionId":"x"}\n'
        )
        assert parse_session_file(ops_only) is None

    def test_malformed_lines_are_skipped(self, tmp_path):
        from intelligent_chat.ingestion.claude_code import parse_session_file

        mixed = tmp_path / "mixed.jsonl"
        mixed.write_text(
            "not json at all\n"
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]},'
            '"uuid":"u1","timestamp":"2026-07-01T10:00:00.000Z","sessionId":"s1",'
            '"cwd":"C:\\\\test\\\\proj","gitBranch":"main"}\n'
        )
        result = parse_session_file(mixed)
        assert result is not None
        assert len(result["messages"]) == 1


# ---------------------------------------------------------------------------
# Copilot connector
# ---------------------------------------------------------------------------

class TestCopilotConnector:
    def test_parse_valid_copilot_file(self):
        from intelligent_chat.ingestion.copilot import parse_copilot_file

        result = parse_copilot_file(FIXTURES / "sample_copilot.md")

        assert result is not None
        assert result["source_type"] == "copilot"
        assert result["title"] == "sqlalchemy-setup"
        assert "async" in result["body"].lower()

    def test_parse_empty_file_returns_none(self, tmp_path):
        from intelligent_chat.ingestion.copilot import parse_copilot_file

        empty = tmp_path / "empty.md"
        empty.write_text("")
        assert parse_copilot_file(empty) is None

    def test_parse_no_frontmatter(self, tmp_path):
        from intelligent_chat.ingestion.copilot import parse_copilot_file

        plain = tmp_path / "plain.md"
        plain.write_text("# Just a heading\n\nSome body text.")
        result = parse_copilot_file(plain)
        assert result is not None
        assert result["title"] == "plain"  # falls back to stem


# ---------------------------------------------------------------------------
# Archive writer
# ---------------------------------------------------------------------------

class TestArchiveWriter:
    def test_archives_file_with_correct_path(self, tmp_path):
        import intelligent_chat.ingestion.archive as archive_mod
        from intelligent_chat.ingestion.archive import archive_file

        source = tmp_path / "session123.jsonl"
        source.write_text('{"type":"user"}')
        archive_dir = tmp_path / "archive"

        archive_mod.ARCHIVE_DIR if hasattr(archive_mod, "ARCHIVE_DIR") else None
        # Patch ARCHIVE_DIR for this test
        with patch("intelligent_chat.ingestion.archive.ARCHIVE_DIR", archive_dir):
            result = archive_file(source, "claude_code", "session123")

        assert result.exists()
        assert result.name == "session123.jsonl"
        assert "claude_code" in str(result)

    def test_archive_is_idempotent(self, tmp_path):
        from intelligent_chat.ingestion.archive import archive_file

        source = tmp_path / "s.jsonl"
        source.write_text("data")
        archive_dir = tmp_path / "archive"

        with patch("intelligent_chat.ingestion.archive.ARCHIVE_DIR", archive_dir):
            p1 = archive_file(source, "claude_code", "s")
            p2 = archive_file(source, "claude_code", "s")

        assert p1 == p2


# ---------------------------------------------------------------------------
# Ingest service
# ---------------------------------------------------------------------------

class TestIngestService:
    def test_ingest_envelope_creates_session_and_messages(self):
        from intelligent_chat.ingestion.claude_code import parse_session_file
        from intelligent_chat.ingestion.service import ingest_envelope

        _, db, workspace_id = make_db()
        envelope = parse_session_file(FIXTURES / "sample_session.jsonl")

        result = ingest_envelope(envelope, db, workspace_id=workspace_id, normalize=False)

        assert result["status"] == "ingested"
        assert not result["skipped"]

        sess = db.get(IngestSession, envelope["session_id"])
        assert sess is not None
        assert sess.token_count == 83

        msgs = db.query(Message).filter_by(session_id=envelope["session_id"]).all()
        assert len(msgs) == 4

    def test_ingest_envelope_is_idempotent(self):
        from intelligent_chat.ingestion.claude_code import parse_session_file
        from intelligent_chat.ingestion.service import ingest_envelope

        _, db, workspace_id = make_db()
        envelope = parse_session_file(FIXTURES / "sample_session.jsonl")

        ingest_envelope(envelope, db, workspace_id=workspace_id, normalize=False)
        result2 = ingest_envelope(envelope, db, workspace_id=workspace_id, normalize=False)

        assert result2["skipped"] is True


# ---------------------------------------------------------------------------
# Normalization pipeline (mocked LLM)
# ---------------------------------------------------------------------------

def _make_tool_input(concepts: list[dict], relationships: list[dict]) -> dict:
    """Return the dict that call_save_knowledge would return after parsing the LLM response."""
    return {"concepts": concepts, "relationships": relationships}


class TestNormalizationPipeline:
    def test_normalize_creates_concepts(self):
        from intelligent_chat.ingestion.claude_code import parse_session_file
        from intelligent_chat.ingestion.service import ingest_envelope
        from intelligent_chat.normalization.pipeline import normalize_session

        _, db, workspace_id = make_db()
        envelope = parse_session_file(FIXTURES / "sample_session.jsonl")
        ingest_envelope(envelope, db, workspace_id=workspace_id, normalize=False)

        tool_input = _make_tool_input(
            concepts=[
                {
                    "action": "create",
                    "title": "SQLAlchemy Async Setup",
                    "type": "decision",
                    "description": "Use create_async_engine with asyncpg for PostgreSQL.",
                    "body": "Use `create_async_engine` with `asyncpg` for production PostgreSQL.",
                    "tags": ["python", "database"],
                    "confidence": "extracted",
                    "scope": "workspace",
                },
                {
                    "action": "create",
                    "title": "Use synchronous engine for this project",
                    "type": "decision",
                    "description": "This project uses sync SQLAlchemy for simplicity.",
                    "body": "Sync engine chosen to avoid asyncio complexity in the CLI.",
                    "tags": ["python", "database"],
                    "confidence": "extracted",
                    "scope": "project",
                },
            ],
            relationships=[],
        )

        with patch("intelligent_chat.normalization.pipeline.call_save_knowledge", return_value=tool_input):
            result = normalize_session(envelope, db, workspace_id, envelope["session_id"])

        assert result["concepts_created"] == 2
        assert result["concepts_updated"] == 0

        workspace_concept = db.query(Concept).filter_by(title="SQLAlchemy Async Setup").first()
        assert workspace_concept is not None
        assert workspace_concept.type == "decision"
        assert workspace_concept.visibility == "workspace"
        assert workspace_concept.project_id is None
        tags = [t.tag for t in workspace_concept.tags]
        assert "python" in tags

        project_concept = db.query(Concept).filter_by(title="Use synchronous engine for this project").first()
        assert project_concept is not None
        assert project_concept.visibility == "project"
        assert project_concept.project_id is not None

    def test_normalize_creates_relationships(self):
        from intelligent_chat.ingestion.claude_code import parse_session_file
        from intelligent_chat.ingestion.service import ingest_envelope
        from intelligent_chat.normalization.pipeline import normalize_session

        _, db, workspace_id = make_db()
        envelope = parse_session_file(FIXTURES / "sample_session.jsonl")
        ingest_envelope(envelope, db, workspace_id=workspace_id, normalize=False)

        tool_input = _make_tool_input(
            concepts=[
                {
                    "action": "create",
                    "title": "SQLAlchemy",
                    "type": "tool",
                    "description": "Python ORM.",
                    "body": "SQLAlchemy is the ORM used in this project.",
                    "tags": ["python", "database"],
                    "confidence": "extracted",
                    "scope": "workspace",
                },
                {
                    "action": "create",
                    "title": "asyncpg",
                    "type": "tool",
                    "description": "Fast async PostgreSQL driver.",
                    "body": "asyncpg is used as the PostgreSQL async driver.",
                    "tags": ["python", "database"],
                    "confidence": "extracted",
                    "scope": "workspace",
                },
            ],
            relationships=[{
                "source_title": "SQLAlchemy",
                "target_title": "asyncpg",
                "relation_type": "uses",
                "confidence": "extracted",
                "evidence_snippet": "Use asyncpg for production PostgreSQL with async SQLAlchemy.",
            }],
        )

        with patch("intelligent_chat.normalization.pipeline.call_save_knowledge", return_value=tool_input):
            result = normalize_session(envelope, db, workspace_id, envelope["session_id"])

        assert result["relationships_created"] == 1
        rel = db.query(Relationship).first()
        assert rel is not None
        assert rel.relation_type == "uses"
        assert rel.evidence_id is not None  # evidence snippet was saved
