"""Auth router — register, login, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from intelligent_chat.api.auth import create_access_token, hash_password, verify_password
from intelligent_chat.api.deps import CurrentUser, get_db
from intelligent_chat.api.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from intelligent_chat.storage.models import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account, a personal workspace, and return a JWT."""
    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=body.email,
        name=body.name,
        role="admin",
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()

    workspace = Workspace(
        name=body.workspace_name,
        owner_id=user.id,
        visibility="private",
    )
    db.add(workspace)
    db.flush()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.commit()

    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return a JWT."""
    user = db.query(User).filter_by(email=body.email).first()
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    """Return the currently authenticated user."""
    return user
