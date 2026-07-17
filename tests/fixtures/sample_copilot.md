---
name: sqlalchemy-setup
description: Notes on setting up SQLAlchemy with async support for the project
---

## SQLAlchemy Async Setup

Use `create_async_engine` with `aiosqlite` for SQLite and `asyncpg` for PostgreSQL.

Install: `pip install sqlalchemy[asyncio] aiosqlite asyncpg`
