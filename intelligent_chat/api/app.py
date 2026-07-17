"""FastAPI application — auth, workspace management, permission-aware search."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intelligent_chat.api.routers import auth, concepts, workspaces

app = FastAPI(
    title="iChat — Collective Memory Platform",
    description="API for ingesting, searching, and exploring AI coding session knowledge.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(concepts.router)


@app.get("/health")
def health():
    return {"status": "ok"}
