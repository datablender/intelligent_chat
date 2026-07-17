"""FastAPI dependencies — DB session, current user, permission checks."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from intelligent_chat.api.auth import decode_access_token
from intelligent_chat.storage.database import SessionLocal
from intelligent_chat.storage.models import (
    ProjectMember,
    User,
    Workspace,
    WorkspaceMember,
)

_bearer = HTTPBearer()

_ROLE_RANK = {"viewer": 0, "editor": 1, "owner": 2}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[object, Depends(get_db)]


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: DbDep,
) -> User:
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Workspace permission
# ---------------------------------------------------------------------------

def _get_workspace_role(db, workspace_id: int, user_id: int) -> str | None:
    """Return the user's role in the workspace, or None if not a member."""
    membership = (
        db.query(WorkspaceMember)
        .filter_by(workspace_id=workspace_id, user_id=user_id)
        .first()
    )
    # Workspace owner always has owner role
    workspace = db.get(Workspace, workspace_id)
    if workspace and workspace.owner_id == user_id:
        return "owner"
    return membership.role if membership else None


def require_workspace_role(min_role: str):
    """Returns a dependency that enforces a minimum workspace role."""
    def _check(
        workspace_id: int,
        user: CurrentUser,
        db: DbDep,
    ) -> WorkspaceMember:
        role = _get_workspace_role(db, workspace_id, user.id)
        if role is None or _ROLE_RANK.get(role, -1) < _ROLE_RANK.get(min_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires workspace role '{min_role}' or higher",
            )
        return role
    return _check


# ---------------------------------------------------------------------------
# Project permission
# ---------------------------------------------------------------------------

def _get_project_role(db, workspace_id: int, project_id: int, user_id: int) -> str | None:
    """Return the effective project role (project override or workspace role)."""
    ws_role = _get_workspace_role(db, workspace_id, user_id)
    proj_member = (
        db.query(ProjectMember)
        .filter_by(project_id=project_id, user_id=user_id)
        .first()
    )
    proj_role = proj_member.role if proj_member else None

    # Take the higher of the two roles
    ws_rank = _ROLE_RANK.get(ws_role or "", -1)
    proj_rank = _ROLE_RANK.get(proj_role or "", -1)
    if ws_rank >= proj_rank:
        return ws_role
    return proj_role


def require_project_role(min_role: str):
    """Returns a dependency that enforces a minimum project role."""
    def _check(
        workspace_id: int,
        project_id: int,
        user: CurrentUser,
        db: DbDep,
    ) -> str:
        role = _get_project_role(db, workspace_id, project_id, user.id)
        if role is None or _ROLE_RANK.get(role, -1) < _ROLE_RANK.get(min_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires project role '{min_role}' or higher",
            )
        return role
    return _check


def accessible_project_ids(db, workspace_id: int, user_id: int) -> list[int] | None:
    """Return list of project IDs the user can access, or None for workspace owners/editors.

    None means "all" — used to skip visibility filtering for users with full access.
    """
    ws_role = _get_workspace_role(db, workspace_id, user_id)
    if ws_role in ("owner", "editor"):
        return None  # sees everything

    # Viewer: only sees workspace-visible content + projects they're a member of
    proj_ids = [
        pm.project_id
        for pm in db.query(ProjectMember).filter_by(user_id=user_id).all()
    ]
    return proj_ids
