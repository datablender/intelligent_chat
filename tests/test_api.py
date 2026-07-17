"""Phase 4 tests — FastAPI auth, workspace management, permission enforcement."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from intelligent_chat.storage.models import Base

# ---------------------------------------------------------------------------
# Test app fixture with in-memory DB
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Return a TestClient wired to an in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    from intelligent_chat.api import app as api_module
    from intelligent_chat.api.deps import get_db

    def override_get_db():
        db = Session(engine)
        try:
            yield db
        finally:
            db.close()

    api_module.app.dependency_overrides[get_db] = override_get_db
    with TestClient(api_module.app) as c:
        yield c
    api_module.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auth — register + login + me
# ---------------------------------------------------------------------------

class TestAuth:
    def test_register_creates_user_and_returns_token(self, client):
        r = client.post("/auth/register", json={
            "email": "alice@example.com",
            "name": "Alice",
            "password": "secret123",
            "workspace_name": "alice-ws",
        })
        assert r.status_code == 201
        assert "access_token" in r.json()

    def test_duplicate_email_returns_409(self, client):
        payload = {"email": "bob@example.com", "name": "Bob",
                   "password": "secret", "workspace_name": "bobs"}
        client.post("/auth/register", json=payload)
        r = client.post("/auth/register", json=payload)
        assert r.status_code == 409

    def test_login_returns_token(self, client):
        client.post("/auth/register", json={
            "email": "carol@example.com", "name": "Carol",
            "password": "mypassword", "workspace_name": "carol",
        })
        r = client.post("/auth/login", json={
            "email": "carol@example.com", "password": "mypassword",
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_wrong_password_returns_401(self, client):
        client.post("/auth/register", json={
            "email": "dave@example.com", "name": "Dave",
            "password": "correct", "workspace_name": "dave",
        })
        r = client.post("/auth/login", json={
            "email": "dave@example.com", "password": "wrong",
        })
        assert r.status_code == 401

    def test_me_returns_current_user(self, client):
        r = client.post("/auth/register", json={
            "email": "eve@example.com", "name": "Eve",
            "password": "evepw", "workspace_name": "eve",
        })
        token = r.json()["access_token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "eve@example.com"

    def test_me_with_invalid_token_returns_401(self, client):
        r = client.get("/auth/me", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

def _register(client, email="user@example.com", name="User", pw="pw", ws="myws"):
    r = client.post("/auth/register", json={
        "email": email, "name": name, "password": pw, "workspace_name": ws,
    })
    return r.json()["access_token"]


class TestWorkspaces:
    def test_list_workspaces_returns_own_workspace(self, client):
        token = _register(client, "frank@x.com", ws="franks-ws")
        r = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        names = [w["name"] for w in r.json()]
        assert "franks-ws" in names

    def test_create_workspace(self, client):
        token = _register(client, "grace@x.com")
        r = client.post("/workspaces",
                        json={"name": "new-ws"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201
        assert r.json()["name"] == "new-ws"

    def test_add_member_requires_owner(self, client):
        owner_token = _register(client, "owner@x.com", ws="shared")
        _register(client, "viewer@x.com", ws="viewers")

        # Get workspace id
        ws_list = client.get("/workspaces",
                             headers={"Authorization": f"Bearer {owner_token}"})
        ws_id = next(w["id"] for w in ws_list.json() if w["name"] == "shared")

        # Add viewer as workspace member
        r = client.post(
            f"/workspaces/{ws_id}/members",
            json={"email": "viewer@x.com", "role": "viewer"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert r.status_code == 201
        assert r.json()["role"] == "viewer"

    def test_viewer_cannot_add_members(self, client):
        owner_token = _register(client, "own2@x.com", ws="own2-ws")
        viewer_token = _register(client, "view2@x.com", ws="view2-ws")
        _register(client, "third@x.com", ws="third-ws")

        ws_list = client.get("/workspaces",
                             headers={"Authorization": f"Bearer {owner_token}"})
        ws_id = next(w["id"] for w in ws_list.json() if w["name"] == "own2-ws")

        # Add viewer2 to own2-ws
        client.post(f"/workspaces/{ws_id}/members",
                    json={"email": "view2@x.com", "role": "viewer"},
                    headers={"Authorization": f"Bearer {owner_token}"})

        # viewer2 tries to add third — should be forbidden
        r = client.post(
            f"/workspaces/{ws_id}/members",
            json={"email": "third@x.com", "role": "viewer"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class TestProjects:
    def test_create_project(self, client):
        token = _register(client, "heidi@x.com", ws="heidi-ws")
        ws_list = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
        ws_id = ws_list.json()[0]["id"]

        r = client.post(
            f"/workspaces/{ws_id}/projects",
            json={"name": "my-project", "description": "Test project"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        assert r.json()["name"] == "my-project"

    def test_viewer_cannot_see_private_project(self, client):
        owner_token = _register(client, "ivan@x.com", ws="ivan-ws")
        viewer_token = _register(client, "judy@x.com", ws="judy-ws")

        ws_list = client.get("/workspaces", headers={"Authorization": f"Bearer {owner_token}"})
        ws_id = next(w["id"] for w in ws_list.json() if w["name"] == "ivan-ws")

        # Add judy as viewer
        client.post(f"/workspaces/{ws_id}/members",
                    json={"email": "judy@x.com", "role": "viewer"},
                    headers={"Authorization": f"Bearer {owner_token}"})

        # Create private project
        client.post(f"/workspaces/{ws_id}/projects",
                    json={"name": "secret-project", "visibility": "private"},
                    headers={"Authorization": f"Bearer {owner_token}"})

        # Judy should not see it
        r = client.get(f"/workspaces/{ws_id}/projects",
                       headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 200
        names = [p["name"] for p in r.json()]
        assert "secret-project" not in names
