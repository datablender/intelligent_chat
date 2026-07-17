"""Workspace and project membership management router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from intelligent_chat.api.deps import (
    CurrentUser,
    _get_workspace_role,
    get_db,
    require_workspace_role,
)
from intelligent_chat.api.schemas import (
    AddMemberRequest,
    MemberOut,
    ProjectCreate,
    ProjectOut,
    WorkspaceCreate,
    WorkspaceOut,
)
from intelligent_chat.storage.models import (
    AuditLog,
    Project,
    ProjectMember,
    User,
    Workspace,
    WorkspaceMember,
)

router = APIRouter(tags=["workspaces"])


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(user: CurrentUser, db: Session = Depends(get_db)):
    """List all workspaces the current user is a member of."""
    owned = db.query(Workspace).filter_by(owner_id=user.id).all()
    member_ws_ids = {
        m.workspace_id
        for m in db.query(WorkspaceMember).filter_by(user_id=user.id).all()
    }
    for ws in owned:
        member_ws_ids.add(ws.id)
    return db.query(Workspace).filter(Workspace.id.in_(member_ws_ids)).all()


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, user: CurrentUser, db: Session = Depends(get_db)):
    """Create a new workspace. The creator becomes the owner."""
    ws = Workspace(name=body.name, owner_id=user.id, visibility=body.visibility)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    db.commit()
    return ws


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("viewer")),
):
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


# ---------------------------------------------------------------------------
# Workspace members
# ---------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_workspace_members(
    workspace_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("viewer")),
):
    members = db.query(WorkspaceMember).filter_by(workspace_id=workspace_id).all()
    result = []
    for m in members:
        member_user = db.get(User, m.user_id)
        result.append(MemberOut(
            id=m.id,
            user_id=m.user_id,
            role=m.role,
            created_at=m.created_at,
            user_email=member_user.email if member_user else "",
            user_name=member_user.name if member_user else "",
        ))
    return result


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_workspace_member(
    workspace_id: int,
    body: AddMemberRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("owner")),
):
    """Add a user to the workspace. Requires owner role."""
    target = db.query(User).filter_by(email=body.email).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    existing = db.query(WorkspaceMember).filter_by(
        workspace_id=workspace_id, user_id=target.id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member")

    member = WorkspaceMember(workspace_id=workspace_id, user_id=target.id, role=body.role)
    db.add(member)
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="create",
        entity_type="member",
        entity_id=target.id,
        changes={"email": body.email, "role": body.role},
    ))
    db.commit()

    return MemberOut(
        id=member.id, user_id=target.id, role=member.role,
        created_at=member.created_at, user_email=target.email, user_name=target.name,
    )


@router.delete("/workspaces/{workspace_id}/members/{target_user_id}", status_code=204)
def remove_workspace_member(
    workspace_id: int,
    target_user_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("owner")),
):
    """Remove a user from the workspace. Cannot remove the owner."""
    ws = db.get(Workspace, workspace_id)
    if ws and ws.owner_id == target_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the workspace owner")
    member = db.query(WorkspaceMember).filter_by(
        workspace_id=workspace_id, user_id=target_user_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="delete",
        entity_type="member",
        entity_id=target_user_id,
    ))
    db.commit()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectOut])
def list_projects(
    workspace_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("viewer")),
):
    ws_role = _get_workspace_role(db, workspace_id, user.id)
    projects = db.query(Project).filter_by(workspace_id=workspace_id).all()
    if ws_role in ("owner", "editor"):
        return projects
    # Viewers only see workspace-visible projects + ones they're a member of
    accessible_ids = {
        pm.project_id
        for pm in db.query(ProjectMember).filter_by(user_id=user.id).all()
    }
    return [p for p in projects if p.visibility == "workspace" or p.id in accessible_ids]


@router.post(
    "/workspaces/{workspace_id}/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    workspace_id: int,
    body: ProjectCreate,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("editor")),
):
    project = Project(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        visibility=body.visibility,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="create",
        entity_type="project",
        entity_id=project.id,
        changes={"name": body.name},
    ))
    db.commit()
    return project


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/members",
    response_model=list[MemberOut],
)
def list_project_members(
    workspace_id: int,
    project_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("viewer")),
):
    members = db.query(ProjectMember).filter_by(project_id=project_id).all()
    result = []
    for m in members:
        u = db.get(User, m.user_id)
        result.append(MemberOut(
            id=m.id, user_id=m.user_id, role=m.role, created_at=m.created_at,
            user_email=u.email if u else "", user_name=u.name if u else "",
        ))
    return result


@router.post(
    "/workspaces/{workspace_id}/projects/{project_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    workspace_id: int,
    project_id: int,
    body: AddMemberRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("editor")),
):
    """Add a user to a project. User must already be a workspace member."""
    target = db.query(User).filter_by(email=body.email).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    ws_role = _get_workspace_role(db, workspace_id, target.id)
    if not ws_role:
        raise HTTPException(
            status_code=400,
            detail="Target user must be a workspace member first",
        )
    existing = db.query(ProjectMember).filter_by(
        project_id=project_id, user_id=target.id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User is already a project member")

    member = ProjectMember(project_id=project_id, user_id=target.id, role=body.role)
    db.add(member)
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="create",
        entity_type="project_member",
        entity_id=target.id,
        changes={"project_id": project_id, "email": body.email, "role": body.role},
    ))
    db.commit()
    return MemberOut(
        id=member.id, user_id=target.id, role=member.role,
        created_at=member.created_at, user_email=target.email, user_name=target.name,
    )
