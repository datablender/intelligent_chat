# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
pip install -e .
pip install ruff pytest pytest-asyncio  # dev tools

# Run tests
pytest -q                              # all tests (80)
pytest tests/test_api.py -v            # single file, verbose
pytest -k "test_insert"                # filter by name

# Lint
ruff check .
ruff check --fix --unsafe-fixes .      # auto-fix

# Database migrations
python -m alembic upgrade head         # apply all migrations
python -m alembic revision --autogenerate -m "description"  # after model changes
python -m alembic downgrade -1         # roll back one

# CLI (after pip install -e .)
ichat --help
ichat init                             # create workspace + user
ichat status                           # summary counts
ichat ingest scan                      # import Claude Code sessions
ichat ingest normalize                 # LLM normalize pending sessions
ichat search query "text"              # keyword search
ichat search semantic "text"           # vector search (needs OPENAI_API_KEY + ichat embed)
ichat embed                            # generate embeddings for semantic search
ichat export okf --output ./kb/        # OKF markdown bundle
ichat export graph --output ./graph.json
ichat governance lint                  # run all 6 lint checks
ichat governance issues                # list open findings
ichat governance resolve <id>          # mark resolved
ichat api                              # start FastAPI server (port 8000)
ichat mcp                              # start MCP server over stdio
```

## Architecture

A collective memory platform that ingests AI coding sessions (Claude Code, Copilot), uses Claude to normalize them into OKF-structured concept pages, and stores them in a relational database. A REST API (FastAPI + JWT) enables multi-user team use. An MCP server exposes the knowledge base as tools for Claude Code during live sessions.

Full user docs: [docs/WIKI.md](docs/WIKI.md)

**Package layout:**
```
intelligent_chat/
  cli/            Typer CLI entrypoints (command: ichat)
  ingestion/      Source connectors (claude_code.py, copilot.py) + raw archive writer
  normalization/  LLM normalization pipeline (calls Claude API via tool-calling)
  storage/        SQLAlchemy models + Alembic migrations + database session
  search/         Full-text search + semantic search (cosine similarity)
  embeddings/     OpenAI embedding generation, cosine similarity math
  export/         OKF markdown bundle (okf.py) + Graphify graph.json (graph.py)
  graph/          Graph builder
  governance/     6 lint check functions + governance service
  api/            FastAPI app, JWT auth, workspace/project routers, Pydantic schemas
  mcp/            MCP server (FastMCP) — 5 tools for Claude Code integration
  config.py       All config via env vars
```

**Key files:**
- [storage/models.py](intelligent_chat/storage/models.py) — all 14 SQLAlchemy models
- [storage/database.py](intelligent_chat/storage/database.py) — engine + session factory
- [config.py](intelligent_chat/config.py) — env var loading
- [normalization/prompts.py](intelligent_chat/normalization/prompts.py) — LLM system prompt + tool schemas
- [api/app.py](intelligent_chat/api/app.py) — FastAPI app with router registration
- [api/deps.py](intelligent_chat/api/deps.py) — JWT auth, role enforcement dependencies
- [mcp/server.py](intelligent_chat/mcp/server.py) — 5 MCP tools (search_knowledge, semantic_search, get_concept, list_recent, save_note)
- [conventions.md](conventions.md) — canonical OKF types, tags, naming rules (fed into LLM prompts)
- [alembic/versions/](alembic/versions/) — 6 migrations; run `alembic upgrade head` after pulling

## Key Conventions

- All config from `intelligent_chat/config.py` — never `os.getenv()` in feature modules
- DB sessions: use `get_session()` from `storage/database.py`; always close or use as context manager
- OKF schema: every concept has a `type` from the canonical list in `conventions.md`; LLM prompts include `conventions.md`
- Any `models.py` change → new Alembic revision before merging
- SQLite migrations on existing tables must use `op.batch_alter_table()` — direct `op.add_column()` + `op.create_foreign_key()` fails on SQLite
- Tests use `StaticPool` for in-memory SQLite (avoids connection-isolation issues where `create_all` and session see different DBs)
- Python must stay `>=3.11,<3.13` — Leiden community detection requires `<3.13`
- Tests use plain pytest functions, not `unittest.TestCase`
- `CurrentUser = Annotated[User, Depends(get_current_user)]` — do NOT add `= Depends()` default to parameters typed with this alias; place before any Query params with defaults
