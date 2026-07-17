from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="contributor")
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    owned_workspaces: Mapped[list["Workspace"]] = relationship(back_populates="owner")
    workspace_memberships: Mapped[list["WorkspaceMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    project_memberships: Mapped[list["ProjectMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    visibility: Mapped[str] = mapped_column(String(50), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    owner: Mapped["User"] = relationship(back_populates="owned_workspaces")
    projects: Mapped[list["Project"]] = relationship(back_populates="workspace")
    sessions: Mapped[list["IngestSession"]] = relationship(back_populates="workspace")
    concepts: Mapped[list["Concept"]] = relationship(back_populates="workspace")
    members: Mapped[list["WorkspaceMember"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # workspace | private  (workspace = all workspace members can see; private = members only)
    visibility: Mapped[str] = mapped_column(String(50), default="workspace")
    attrs: Mapped[dict | None] = mapped_column(JSON)

    workspace: Mapped["Workspace"] = relationship(back_populates="projects")
    sessions: Mapped[list["IngestSession"]] = relationship(back_populates="project")
    concepts: Mapped[list["Concept"]] = relationship(back_populates="project")
    members: Mapped[list["ProjectMember"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class IngestSession(Base):
    """A single ingested AI coding session (Claude Code, Copilot, etc.)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id"))
    source_type: Mapped[str] = mapped_column(String(50))  # claude_code | copilot
    source_id: Mapped[str | None] = mapped_column(String(255))
    raw_archive_path: Mapped[str | None] = mapped_column(String(1024))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending | normalized | error

    workspace: Mapped["Workspace"] = relationship(back_populates="sessions")
    project: Mapped[Optional["Project"]] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(50))  # user | assistant | tool
    content: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    tool_name: Mapped[str | None] = mapped_column(String(255))
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    attrs: Mapped[dict | None] = mapped_column(JSON)

    session: Mapped["IngestSession"] = relationship(back_populates="messages")


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    # NULL = workspace-wide shared knowledge; set = project-specific knowledge
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(100))
    body: Mapped[str | None] = mapped_column(Text)
    resource: Mapped[str | None] = mapped_column(String(1024))
    confidence: Mapped[str] = mapped_column(String(50), default="extracted")  # extracted | inferred
    # workspace | project | private
    visibility: Mapped[str] = mapped_column(String(50), default="workspace")
    # JSON-encoded float list; None until ichat embed runs
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="concepts")
    project: Mapped[Optional["Project"]] = relationship(back_populates="concepts")
    tags: Mapped[list["ConceptTag"]] = relationship(back_populates="concept", cascade="all, delete-orphan")
    outgoing: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.source_concept_id",
        back_populates="source_concept",
    )
    incoming: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.target_concept_id",
        back_populates="target_concept",
    )


class ConceptTag(Base):
    __tablename__ = "concept_tags"

    concept_id: Mapped[int] = mapped_column(Integer, ForeignKey("concepts.id"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(100), primary_key=True)

    concept: Mapped["Concept"] = relationship(back_populates="tags")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    session_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("sessions.id"))
    snippet: Mapped[str | None] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    session: Mapped[Optional["IngestSession"]] = relationship(back_populates="evidence")
    relationships: Mapped[list["Relationship"]] = relationship(back_populates="evidence")


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    source_concept_id: Mapped[int] = mapped_column(Integer, ForeignKey("concepts.id"))
    target_concept_id: Mapped[int] = mapped_column(Integer, ForeignKey("concepts.id"))
    relation_type: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[str] = mapped_column(String(50), default="extracted")  # extracted | inferred
    evidence_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("evidence.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    source_concept: Mapped["Concept"] = relationship(
        foreign_keys=[source_concept_id], back_populates="outgoing"
    )
    target_concept: Mapped["Concept"] = relationship(
        foreign_keys=[target_concept_id], back_populates="incoming"
    )
    evidence: Mapped[Optional["Evidence"]] = relationship(back_populates="relationships")


class GovernanceIssue(Base):
    __tablename__ = "governance_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    issue_type: Mapped[str] = mapped_column(String(100))  # contradiction | orphan | staleness | broken_link | coverage_gap | confidence_drift
    severity: Mapped[str] = mapped_column(String(50))  # high | medium | low
    affected_entity_id: Mapped[int | None] = mapped_column(Integer)
    affected_entity_type: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class OKFExportLog(Base):
    __tablename__ = "okf_export_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    exported_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    export_path: Mapped[str] = mapped_column(String(1024))
    record_count: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    """Append-only record of every create/update/delete on concepts and relationships."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))  # create | update | delete
    entity_type: Mapped[str] = mapped_column(String(100))  # concept | relationship | member
    entity_id: Mapped[int | None] = mapped_column(Integer)
    # {field: [old_value, new_value]} for updates; full snapshot for creates
    changes: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class WorkspaceMember(Base):
    """Grants a user access to a workspace with a role.

    Roles: owner | editor | viewer
    - owner: full control including deleting the workspace and managing members
    - editor: can ingest sessions, create/update concepts, run governance
    - viewer: read-only access to all workspace-visible content
    """

    __tablename__ = "workspace_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    # owner | editor | viewer
    role: Mapped[str] = mapped_column(String(50), default="viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="workspace_memberships")


class ProjectMember(Base):
    """Grants a user access to a specific project, overriding their workspace role.

    A workspace viewer can be promoted to editor on a single project.
    A user with no workspace membership cannot be granted project access.
    Roles: owner | editor | viewer (same semantics as WorkspaceMember, project-scoped).
    """

    __tablename__ = "project_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    # owner | editor | viewer
    role: Mapped[str] = mapped_column(String(50), default="viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="project_memberships")
