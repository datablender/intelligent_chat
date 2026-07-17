"""Pydantic schemas for request and response bodies."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    workspace_name: str = "default"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class WorkspaceOut(BaseModel):
    id: int
    name: str
    visibility: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceCreate(BaseModel):
    name: str
    visibility: str = "private"


class MemberOut(BaseModel):
    id: int
    user_id: int
    role: str
    created_at: datetime
    user_email: str = ""
    user_name: str = ""

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class ProjectOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None
    visibility: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    visibility: str = "workspace"


# ---------------------------------------------------------------------------
# Concepts / Search
# ---------------------------------------------------------------------------

class ConceptOut(BaseModel):
    id: int
    title: str
    type: str
    description: str | None
    confidence: str
    visibility: str
    project_id: int | None
    tags: list[str] = []
    source_session: str | None = None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    total: int
    results: list[dict]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: int | None
    changes: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
