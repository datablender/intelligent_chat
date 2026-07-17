"""Ingest service — orchestrates connector → archive → DB → normalization."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from intelligent_chat.config import DEFAULT_WORKSPACE_ID
from intelligent_chat.ingestion import archive, claude_code, copilot
from intelligent_chat.storage.models import IngestSession, Message, Project, Workspace


def _ensure_workspace(db: Session, workspace_id: int) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise RuntimeError(
            f"Workspace {workspace_id} not found. Run `ichat workspace create` first."
        )
    return workspace


def _get_or_create_project(db: Session, workspace_id: int, name: str) -> Project:
    project = db.query(Project).filter_by(workspace_id=workspace_id, name=name).first()
    if not project:
        project = Project(workspace_id=workspace_id, name=name)
        db.add(project)
        db.flush()
    return project


def _session_exists(db: Session, session_id: str) -> bool:
    return db.get(IngestSession, session_id) is not None


def ingest_envelope(
    envelope: dict,
    db: Session,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    normalize: bool = True,
) -> dict:
    """Persist a parsed session envelope to the DB and optionally normalize it.

    Returns a result dict with keys: session_id, status, skipped.
    """
    session_id: str = envelope["session_id"]

    if _session_exists(db, session_id):
        return {"session_id": session_id, "status": "skipped", "skipped": True}

    _ensure_workspace(db, workspace_id)
    project = _get_or_create_project(db, workspace_id, envelope.get("project_name", "unknown"))

    # Archive raw file
    raw_path: Path | None = envelope.get("raw_path")
    archive_path: str | None = None
    if raw_path and raw_path.exists():
        archived = archive.archive_file(raw_path, envelope["source_type"], session_id)
        archive_path = str(archived)

    # Write session record
    sess = IngestSession(
        id=session_id,
        workspace_id=workspace_id,
        project_id=project.id,
        source_type=envelope["source_type"],
        raw_archive_path=archive_path,
        started_at=envelope.get("started_at"),
        ended_at=envelope.get("ended_at"),
        token_count=envelope.get("token_count", 0),
        status="pending",
    )
    db.add(sess)

    # Write messages
    for msg in envelope.get("messages", []):
        db.add(Message(
            session_id=session_id,
            role=msg["role"],
            content=msg.get("content"),
            timestamp=msg.get("timestamp"),
            tool_name=msg.get("tool_name"),
            token_count=msg.get("token_count", 0),
            attrs=msg.get("attrs"),
        ))

    db.commit()

    if normalize:
        from intelligent_chat.normalization.pipeline import normalize_session
        norm_result = normalize_session(envelope, db, workspace_id, session_id)
        return {"session_id": session_id, "status": "normalized", "skipped": False, **norm_result}

    return {"session_id": session_id, "status": "ingested", "skipped": False}


def scan_and_ingest(
    db: Session,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    normalize: bool = True,
    source: str = "claude_code",
    project: str | None = None,
) -> list[dict]:
    """Scan the configured source directory and ingest all new sessions.

    project filters Claude Code ingestion to a specific project slug, partial name,
    or real filesystem path (e.g. "C:\\Users\\sujay\\repos\\myproject").
    """
    results: list[dict] = []

    if source == "claude_code":
        for envelope in claude_code.iter_sessions(project=project):
            result = ingest_envelope(envelope, db, workspace_id, normalize=normalize)
            results.append(result)
    elif source == "copilot":
        for envelope in copilot.iter_sessions():
            result = ingest_envelope(envelope, db, workspace_id, normalize=normalize)
            results.append(result)

    return results


def reprocess_session(session_id: str, db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict:
    """Re-run LLM normalization for a session from its raw archive."""
    from intelligent_chat.ingestion import claude_code as cc

    sess = db.get(IngestSession, session_id)
    if not sess:
        raise ValueError(f"Session {session_id} not found in database.")

    archive_path = sess.raw_archive_path
    if not archive_path or not Path(archive_path).exists():
        raise ValueError(f"Raw archive not found for session {session_id}.")

    if sess.source_type == "claude_code":
        envelope = cc.parse_session_file(Path(archive_path))
    else:
        raise NotImplementedError(f"Reprocess not yet supported for source type: {sess.source_type}")

    if not envelope:
        raise ValueError(f"Could not parse archive file: {archive_path}")

    from intelligent_chat.normalization.pipeline import normalize_session
    result = normalize_session(envelope, db, workspace_id, session_id)
    return {"session_id": session_id, **result}
