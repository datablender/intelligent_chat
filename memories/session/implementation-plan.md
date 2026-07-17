# Implementation Plan: Collective Memory Platform

## MVP Definition

The MVP delivers: import Claude Code transcripts → LLM normalizes into concept pages → store in database → search → export OKF bundle.

This covers Phases 0 through 2. Everything after is post-MVP.

## Phase 0 — Foundation

### Goals
- Establish the project skeleton, tech stack, schema, and conventions
- Produce no features users can run, but every decision that gates Phase 1

### Tech stack decisions (all must be made in this phase)
- Python 3.11 (hard ceiling — Leiden requires < 3.13)
- FastAPI for the eventual API layer
- SQLAlchemy 2.0 (async) as ORM
- Alembic for migrations
- Typer for CLI
- Anthropic SDK for LLM calls
- uv as package manager
- ruff for linting
- pytest + pytest-asyncio for testing
- PostgreSQL as the multi-user backend; SQLite as the local mode backend

### Tasks

1. Replace the current scaffold with the real package structure:
   ```
   intelligent_chat/
     cli/          Typer entrypoints
     ingestion/    connectors and raw archive
     normalization/ LLM normalization pipeline
     storage/      SQLAlchemy models + Alembic migrations
     search/       search layer
     graph/        graph builder and export
     governance/   lint operations
     export/       OKF and graph export
   tests/
   archive/        raw source files (gitignored)
   memories/session/ specification docs
   conventions.md  OKF schema doc
   .env.example
   pyproject.toml
   ```

2. Define the full database schema in SQLAlchemy models covering:
   `users`, `workspaces`, `projects`, `sessions`, `messages`, `concepts`,
   `concept_tags`, `relationships`, `evidence`, `governance_issues`, `okf_export_log`
   All tables include `workspace_id` and relevant foreign keys from day one.

3. Write the first Alembic migration from the models.

4. Write `conventions.md` defining:
   - Canonical `type` values: `decision`, `solution`, `pattern`, `tool`, `project`, `question`, `concept`, `error`, `workaround`
   - Canonical tag taxonomy (language, domain, status tags)
   - Naming rules for concept titles
   - Cross-linking conventions

5. Add ruff configuration and a GitHub Actions workflow that runs `ruff check` and `pytest` on every push.

6. Verify the SQLite and PostgreSQL backends both work with the same models (integration test with both).

### Deliverables
- Full package structure with empty module stubs
- SQLAlchemy models + first migration
- `conventions.md`
- CI workflow
- Both DB backends tested

---

## Phase 1 — Ingestion and LLM Normalization

### Goals
- Capture Claude Code sessions automatically via pre-compaction hook
- Capture Copilot sessions via manual or directory scan
- Normalize raw transcripts into concept pages using Claude
- Store everything in the database

### Tasks

1. **Claude Code connector**
   - Scan `~/.claude/projects/` for JSONL files
   - Decode Base64 encoding (adapt parsing from claude-conversation-extractor)
   - Extract: session id, project name, started_at, ended_at, messages (role, content, timestamp, tool_name, token_count), total token count
   - Write parsed session + messages to DB

2. **Raw archive writer**
   - Before any processing, copy the source file to `./archive/raw/{source_type}/{YYYY-MM-DD}/{session_id}.{ext}`
   - Record `raw_archive_path` on the session record
   - Files are read-only after write; never overwrite

3. **Pre-compaction hook registration**
   - `ingest hook install` writes the hook entry to `~/.claude/settings.json`
   - Hook calls `intelligent_chat ingest --source claude-code --session <id>` when Claude Code compacts a session

4. **Copilot connector**
   - Scan VS Code workspace storage path for memory-tool markdown files
   - Parse YAML frontmatter + body
   - Map to the same normalized session/concept envelope as the Claude Code connector

5. **LLM normalization pipeline**
   - Build the normalization prompt: full transcript + current concept index (titles + one-line descriptions only)
   - Include `conventions.md` content in the system prompt so the LLM draws from canonical types and tags
   - Call Claude API (configurable model; default `claude-sonnet-5`)
   - Parse structured response specifying new concepts, concept updates, new relationships, and evidence snippets
   - Write all records in a single database transaction
   - Log the normalization run to `okf_export_log` (session id, model used, concepts created, concepts updated)

6. **Re-processing support**
   - `ingest reprocess --session <id>` re-runs normalization from the raw archive using the current prompt and conventions
   - Useful when the normalization prompt improves

7. **Tests**
   - Unit tests for each connector's parsing logic with fixture files (valid, malformed, partial)
   - Integration test: ingest a real Claude Code JSONL fixture → verify DB records created correctly
   - Mock the Claude API in unit tests; use a real call in a separate integration test guarded by an env flag

### Deliverables
- `ingest` CLI command (scan, ingest file, ingest session, hook install, reprocess)
- Claude Code connector with Base64 decode
- Copilot connector
- Raw archive writer
- LLM normalization pipeline with structured output parsing
- Test suite with fixtures

---

## Phase 2 — Search and OKF Export

### Goals
- Make the knowledge base searchable
- Produce OKF-compatible exports that work with Graphify and Obsidian

### Tasks

1. **Full-text search**
   - PostgreSQL: create tsvector columns on `concepts.title`, `concepts.body`, `messages.content`; add GIN indexes
   - SQLite: use FTS5 virtual tables over the same columns
   - Abstract behind a `SearchService` so the backend is swappable

2. **Search CLI**
   - `search query "<text>"` — full-text search with ranked results
   - `search filter --type decision --tag python --from 2026-01-01` — metadata filters
   - `search session <id>` — show all concepts extracted from a session
   - Results show: concept title, type, one-line description, source session, confidence

3. **OKF export**
   - `export okf --output ./knowledge-base/` generates:
     - One `.md` file per concept with YAML frontmatter (all OKF fields) + body
     - Cross-links rendered as relative markdown links between concept files
     - `index.md` — concept catalog grouped by type, one-line summaries
     - `log.md` — append-only record of ingests, exports, and governance runs
   - Export is idempotent: re-running overwrites only changed files
   - Record export in `okf_export_log`

4. **Graphify-compatible graph.json export**
   - `export graph --output ./graphify-out/graph.json`
   - Nodes: concepts, sessions, projects
   - Edges: all `relationships` records with type and confidence
   - Format matches Graphify's expected schema so `graphify serve graph.json` works immediately

5. **Tests**
   - Search returns expected results for known fixture data
   - OKF export produces valid YAML frontmatter on every file
   - graph.json passes Graphify schema validation

### Deliverables
- `search` CLI command
- `export okf` command
- `export graph` command
- Full-text search with metadata filters on both DB backends
- OKF bundle readable by Graphify and Obsidian

---

## Phase 3 — Graph Layer and Governance

### Goals
- Wire up Graphify for interactive graph visualization
- Implement the Lint operation to keep the knowledge base healthy

### Tasks

1. **Graphify integration**
   - `graph visualize` runs `graphify extract ./knowledge-base/ --backend claude` and opens the resulting `graph.html`
   - `graph serve` runs `graphify serve graph.json` for MCP access
   - `graph reflect` runs `graphify reflect` to incorporate query history
   - Document the Leiden community detection constraint (Python < 3.13) in setup docs

2. **God nodes**
   - After graph build, compute the top 10 concepts by edge count
   - Store as a manifest file and surface in `search` results as recommended starting points

3. **Governance lint operations**
   - `governance lint` runs all checks and prints findings
   - Implement each check as a separate query against the DB:
     - **Contradiction**: flag concept pairs sharing a `contradicts` edge for human review
     - **Orphan**: concepts with zero relationships after N days
     - **Staleness**: concepts with `updated_at` > 30 days while sessions referencing them continued
     - **Broken link**: cross-references in concept bodies pointing to non-existent titles
     - **Coverage gap**: extract frequent noun phrases from recent sessions; flag topics with no matching concept
     - **Confidence drift**: inferred edges not reinforced by any evidence in the last N sessions
   - Each finding written to `governance_issues` table

4. **Governance CLI**
   - `governance lint` — run all checks
   - `governance issues` — list open issues by severity
   - `governance resolve <id> --note "..."` — mark resolved

5. **Tests**
   - Each lint check tested with fixture data that triggers it
   - graph.json export produces a valid Graphify-compatible file

### Deliverables
- `graph` CLI command (visualize, serve, reflect)
- God nodes computation
- All six lint checks implemented
- `governance` CLI command

---

## Phase 4 — Multi-User and Collaboration

### Goals
- Add authentication, workspaces, and permissions
- Enable shared knowledge bases across teams

### Tasks

1. User registration and login (JWT or session-based auth via FastAPI)
2. Workspace creation and membership management
3. Role-based permission enforcement at the service layer (read, write, admin)
4. API endpoints for all ingestion, search, and export operations (the CLI becomes a thin wrapper over the API)
5. Audit log: record every create/update/delete on concepts and relationships
6. Concept diff history: store body diffs so changes are reviewable
7. Invite flow: invite teammates to a workspace by email

### Deliverables
- Auth endpoints (register, login, token refresh)
- Workspace management endpoints
- Permission enforcement on all existing operations
- Audit log table populated on all writes
- Concept history diff viewer in CLI

---

## Phase 5 — Semantic Retrieval

### Goals
- Upgrade search from keyword to hybrid lexical + semantic

### Tasks

1. Embedding generation for concept bodies using Anthropic or OpenAI embeddings API
2. pgvector extension for PostgreSQL; fallback for SQLite (in-process vector search)
3. Hybrid retrieval: combine lexical score + cosine similarity, rerank results
4. Embedding update pipeline: re-embed concepts when their body changes
5. Recommendation engine: given a concept, suggest related concepts with no direct relationship (gap detection)

### Deliverables
- Embedding pipeline
- Hybrid search endpoint
- Recommendation API

---

## Phase 6 — Advanced UI and Agent Integration

### Goals
- Make the system usable in everyday workflows without the CLI

### Tasks

1. Web dashboard (FastAPI + HTMX or lightweight React): search, concept browser, graph view, workspace management
2. REST API documentation (auto-generated via FastAPI's OpenAPI)
3. MCP integration: `graphify serve` exposed as a registered MCP tool in Claude Code
4. Pre-built connector templates for new source types
5. Public deployment guide (Docker Compose stack with PostgreSQL)

### Deliverables
- Web UI
- Full REST API with OpenAPI docs
- MCP integration documented and tested
- Docker Compose deployment

---

## Release Sequence

| Release | Phases | Capability |
|---|---|---|
| MVP | 0–2 | Import Claude Code + Copilot → LLM normalize → store → search → OKF export |
| v0.2 | 3 | Graph visualization via Graphify + governance lint |
| v0.3 | 4 | Multi-user workspaces, auth, permissions |
| v0.4 | 5 | Semantic + hybrid search, recommendations |
| v1.0 | 6 | Web UI, REST API, MCP, Docker deployment |

---

## Phase 0 Immediate Next Steps

The repo is currently a bare scaffold. These tasks begin Phase 0:

1. Add `pyproject.toml` replacing `requirements.txt`; configure uv, ruff, pytest
2. Create the package directory structure with empty stubs
3. Write SQLAlchemy models for all core tables
4. Run first Alembic migration against SQLite to verify
5. Write `conventions.md` with initial type and tag taxonomy
6. Add GitHub Actions CI (ruff + pytest)
