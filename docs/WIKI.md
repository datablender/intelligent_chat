# iChat Wiki

> A collective memory platform that turns AI coding sessions into searchable, shareable knowledge.

---

## Table of Contents

1. [What Is This?](#1-what-is-this)
2. [How It Works](#2-how-it-works)
3. [Architecture](#3-architecture)
4. [Setup & Installation](#4-setup--installation)
5. [Usage](#5-usage)
   - [First-time setup](#51-first-time-setup)
   - [Ingesting sessions](#52-ingesting-sessions)
   - [Searching the knowledge base](#53-searching-the-knowledge-base)
   - [Semantic search](#54-semantic-search)
   - [Exporting](#55-exporting)
   - [Governance](#56-governance)
   - [REST API](#57-rest-api)
   - [MCP server (Claude Code integration)](#58-mcp-server-claude-code-integration)
6. [Configuration Reference](#6-configuration-reference)
7. [The Knowledge Model](#7-the-knowledge-model)
8. [Multi-User and Teams](#8-multi-user-and-teams)
9. [Development Guide](#9-development-guide)

---

## 1. What Is This?

Every time you work with Claude Code or GitHub Copilot, you produce valuable knowledge — solutions to hard problems, architectural decisions, patterns that work, errors you learned from. But when the session ends, that knowledge disappears. The next session starts from scratch. Your teammates never see it.

iChat fixes this. It watches your AI sessions, reads the transcripts, and uses an LLM (Claude) to extract structured "concept pages" — like a wiki that writes itself. Those pages are stored in a database, linked to each other, searchable by text or semantic similarity, and exportable as Markdown.

The MCP server goes one step further: it plugs the knowledge base directly into Claude Code. While you're working, Claude can search past sessions and surface relevant knowledge without you having to ask.

**The core promise:** every session makes the knowledge base smarter. The more you use it, the more useful it gets.

---

## 2. How It Works

The platform has three core operations:

### Ingest
When a Claude Code session ends or you run `ichat ingest scan`, the platform:
1. Finds new session transcripts in `~/.claude/projects/`
2. Copies them to a local archive (never modified after that)
3. Sends the transcript to Claude with a normalization prompt
4. Claude reads it and decides which concept pages to create or update
5. The concepts and relationships are written to the database

The LLM is an **active author**, not a parser. It decides what's worth keeping, how to frame it, and how it connects to what's already known.

### Query
You search the knowledge base by text keyword, metadata filter, or semantic similarity. Results are ranked by relevance. You can also explore via the graph export.

### Lint (Governance)
A health check that scans the knowledge base for problems:
- **Contradiction**: two concepts directly contradict each other
- **Orphan**: a concept with no connections after 7 days
- **Staleness**: a concept that hasn't been updated while related sessions continued
- **Broken link**: a cross-reference pointing to a concept that doesn't exist
- **Coverage gap**: a normalized session that produced zero concept pages
- **Confidence drift**: an inferred relationship with no supporting evidence after 14 days

Lint findings are stored and can be reviewed and resolved via CLI.

---

## 3. Architecture

```
intelligent_chat/
  cli/            Command-line interface (ichat command)
  ingestion/      Connectors: Claude Code (JSONL), Copilot (Markdown)
  normalization/  LLM pipeline: sends transcript → Claude → parses tool calls → writes DB
  storage/        SQLAlchemy models, Alembic migrations, DB session factory
  search/         Text search + semantic (embedding) search
  embeddings/     OpenAI embedding generation, cosine similarity
  export/         OKF Markdown bundle export, Graphify graph.json export
  graph/          Graph builder
  governance/     6 lint check functions, governance service
  api/            FastAPI REST API (auth, workspaces, concepts)
  mcp/            MCP server (Claude Code tool integration)
  config.py       All env var loading — import from here, never os.getenv directly
```

### Database tables

| Table | Purpose |
|---|---|
| `users` | User accounts with password hashes |
| `workspaces` | Top-level containers for all knowledge |
| `workspace_members` | Who belongs to a workspace (owner / editor / viewer) |
| `projects` | Sub-groups within a workspace (e.g. one per codebase) |
| `project_members` | Project-level role overrides |
| `sessions` | One row per ingested AI session |
| `messages` | Individual messages within a session |
| `concepts` | Structured knowledge pages extracted by the LLM |
| `concept_tags` | Many-to-many tags on concepts |
| `relationships` | Typed links between concepts (uses, solves, contradicts, etc.) |
| `evidence` | Source snippets supporting a relationship |
| `governance_issues` | Lint findings |
| `okf_export_log` | Record of every OKF export run |
| `audit_log` | Append-only log of create/update/delete events |

---

## 4. Setup & Installation

### Prerequisites
- Python 3.11 or 3.12 (not 3.13 — the graph library requires `< 3.13`)
- `ANTHROPIC_API_KEY` for LLM normalization
- `OPENAI_API_KEY` (optional) for semantic search

### Install

```bash
git clone <repo>
cd intelligent_chat

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Mac/Linux

# Install the package and dev tools
pip install -e .
pip install ruff pytest pytest-asyncio
```

### Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=sqlite:///./ichat.db   # default, works out of the box
DEFAULT_WORKSPACE_ID=1
```

### Apply migrations

```bash
python -m alembic upgrade head
```

### Verify

```bash
ichat --help
pytest -q    # should show 80 passed
```

---

## 5. Usage

### 5.1 First-Time Setup

Create your workspace and default user:

```bash
ichat init --name "my-workspace" --email "you@example.com" --display-name "Your Name"
```

Check that it worked:

```bash
ichat status
```

Output:
```
Sessions:      0 total, 0 normalized
Concepts:      0
Relationships: 0
```

---

### 5.2 Ingesting Sessions

#### Scan and ingest Claude Code sessions

```bash
ichat ingest scan
```

This scans `~/.claude/projects/` for sessions that haven't been imported yet, archives them, and writes them to the database. To target a specific project folder:

```bash
ichat ingest scan --project ~/code/my-app
```

#### Normalize sessions into concept pages

After ingestion, sessions have raw messages but no concept pages yet. Normalization sends each session to Claude for extraction:

```bash
ichat ingest normalize
```

This processes all sessions with status `pending`. You can normalize a single session:

```bash
ichat ingest normalize --session-id <session-uuid>
```

#### Re-process with improved prompts

If you improve the normalization prompt (or update `conventions.md`), you can re-run normalization on existing sessions:

```bash
ichat ingest reprocess --session-id <session-uuid>
```

#### Auto-capture with the Claude Code hook

Install the hook so sessions are captured automatically when Claude Code compacts a conversation:

```bash
ichat ingest hook install
```

This writes to `~/.claude/settings.json`. From that point, every session compaction triggers an automatic ingest.

#### Ingest a Copilot session

```bash
ichat ingest copilot --path "~/.../workspaceStorage/<hash>/memfs/"
```

---

### 5.3 Searching the Knowledge Base

#### Text search

```bash
ichat search query "SQLAlchemy migration"
```

Output:
```
3 result(s) for 'SQLAlchemy migration':

  [pattern] Alembic Batch Mode for SQLite
  Use batch_alter_table when adding columns or FK constraints on SQLite
  confidence: extracted  source: session:abc123

  [decision] PostgreSQL vs SQLite Strategy
  SQLite for local dev, PostgreSQL for teams
  ...
```

#### Filter by type or tag

```bash
ichat search query "auth" --type decision
ichat search query "database" --tag postgresql
ichat search query "error" --from 2026-01-01 --to 2026-06-30
```

Available types: `decision`, `solution`, `pattern`, `tool`, `concept`, `project`, `question`, `error`, `workaround`, `reference`

#### Search sessions (by message content)

```bash
ichat search sessions "bcrypt password hashing"
```

#### Show all concepts from a specific session

```bash
ichat search session <session-uuid>
```

---

### 5.4 Semantic Search

Semantic search finds concepts by meaning, not just keywords. It's useful when you know what you're looking for conceptually but don't know the exact terms used.

**Requires:** `OPENAI_API_KEY` in `.env`

**Step 1** — generate embeddings for all concepts (run once, then after new normalizations):

```bash
ichat embed
```

To regenerate all embeddings (e.g. after changing the embedding model):

```bash
ichat embed --force
```

**Step 2** — search:

```bash
ichat search semantic "how do we handle database connection pooling"
```

Options:
```bash
ichat search semantic "query text" --limit 20 --min-score 0.4
```

`--min-score` is the cosine similarity threshold (0–1). Lower values return more results but may be less relevant. Default is `0.5`.

---

### 5.5 Exporting

#### OKF Markdown bundle

Exports the entire knowledge base as one `.md` file per concept, readable by Obsidian, Graphify, or any Markdown viewer:

```bash
ichat export okf --output ./knowledge-base/
```

This creates:
- `knowledge-base/<type>/<concept-title>.md` — one file per concept with YAML frontmatter
- `knowledge-base/index.md` — full catalog grouped by type
- `knowledge-base/log.md` — append-only export log

#### Graphify-compatible graph.json

Exports the knowledge graph as a JSON file for interactive visualization:

```bash
ichat export graph --output ./graphify-out/graph.json
```

Then open it with Graphify:
```bash
graphify serve ./graphify-out/graph.json
```

---

### 5.6 Governance

Run all lint checks against the knowledge base:

```bash
ichat governance lint
```

Output:
```
Governance lint complete.
Total: 5 issue(s) found
  high: 1   medium: 2   low: 2

By check:
  orphan: 3
  staleness: 1
  broken_link: 1
```

Run specific checks only:

```bash
ichat governance lint --check orphan --check staleness
```

List open issues:

```bash
ichat governance issues
ichat governance issues --severity high
ichat governance issues --type orphan
ichat governance issues --resolved   # show resolved ones too
```

Resolve an issue:

```bash
ichat governance resolve 42 --note "Reviewed — concept is intentionally standalone"
```

---

### 5.7 REST API

Start the API server:

```bash
ichat api
```

Or with custom host/port:

```bash
ichat api --host 0.0.0.0 --port 8080 --reload
```

The server starts at `http://127.0.0.1:8000`. Interactive API docs are at `http://127.0.0.1:8000/docs`.

**Key endpoints:**

| Method | Path | What it does |
|---|---|---|
| `POST` | `/auth/register` | Create account + workspace, get JWT |
| `POST` | `/auth/login` | Login, get JWT |
| `GET` | `/auth/me` | Current user info |
| `GET` | `/workspaces` | List your workspaces |
| `POST` | `/workspaces` | Create a workspace |
| `POST` | `/workspaces/{id}/members` | Add a team member |
| `GET` | `/workspaces/{id}/projects` | List projects |
| `POST` | `/workspaces/{id}/projects` | Create a project |
| `GET` | `/workspaces/{id}/concepts/search?q=...` | Search concepts |
| `GET` | `/workspaces/{id}/concepts/search?q=...&semantic=true` | Semantic search |
| `GET` | `/workspaces/{id}/concepts/{id}` | Get a concept |
| `GET` | `/workspaces/{id}/audit-log` | Audit log |

**Authentication:** All endpoints (except `/auth/*`) require a Bearer token:
```
Authorization: Bearer <token>
```

**Register and search example:**
```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","name":"Your Name","password":"secret","workspace_name":"my-ws"}'

# Search (use the token from above)
curl "http://localhost:8000/workspaces/1/concepts/search?q=migrations" \
  -H "Authorization: Bearer <token>"
```

---

### 5.8 MCP Server (Claude Code Integration)

The MCP server is the most powerful way to use iChat. It connects the knowledge base directly to Claude Code so that Claude can search past sessions and save insights during live work — without you having to switch context.

#### Setup

The `.mcp.json` file in this repo root already configures the MCP server. Claude Code detects it automatically when you open this project.

For global access across all your projects, add this to `~/.claude/mcp_settings.json`:

```json
{
  "mcpServers": {
    "ichat-memory": {
      "command": "ichat",
      "args": ["mcp"],
      "env": {
        "DATABASE_URL": "sqlite:///C:/path/to/your/ichat.db",
        "DEFAULT_WORKSPACE_ID": "1"
      }
    }
  }
}
```

#### Available tools

Once connected, Claude Code has access to these tools:

| Tool | What Claude can do |
|---|---|
| `search_knowledge` | Search the KB by keyword before solving a problem |
| `semantic_search` | Search by meaning (needs `OPENAI_API_KEY` + `ichat embed`) |
| `get_concept` | Read the full body of a concept found in search results |
| `list_recent` | See what the team learned in the last N days |
| `save_note` | Save an insight or decision to the KB during this session |

#### How it works in practice

When Claude Code starts a new session, it can automatically check the knowledge base:

> "Before I help with the database migration, let me check if we've solved this before..."
> *[calls search_knowledge("SQLAlchemy migration SQLite")]*
> "Found 2 relevant concepts: 'Alembic Batch Mode for SQLite' and 'Migration Testing Strategy'. Here's what we learned..."

At the end of a session, it can save what was discovered:

> *[calls save_note(title="JWT Key Length Warning", type="error", description="PyJWT warns when HMAC key is under 32 bytes")]*
> "Saved to the knowledge base."

#### Start the MCP server manually (for debugging)

```bash
ichat mcp
```

This runs in stdio mode. In normal use, Claude Code starts it automatically.

---

## 6. Configuration Reference

All configuration is via environment variables, loaded from `.env`. Never call `os.getenv()` directly in feature code — import from `intelligent_chat/config.py`.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for LLM normalization |
| `DEEPSEEK_API_KEY` | — | Alternative LLM provider (takes priority if set) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API endpoint |
| `LLM_PROVIDER` | auto-detected | Force `anthropic` or `deepseek` |
| `NORMALIZATION_MODEL` | `claude-sonnet-5` | LLM model used for normalization |
| `DATABASE_URL` | `sqlite:///./ichat.db` | SQLite (local) or PostgreSQL URL |
| `DEFAULT_WORKSPACE_ID` | `1` | Workspace used by CLI commands |
| `ARCHIVE_DIR` | `./archive/raw` | Where raw session files are copied |
| `CLAUDE_CODE_DIR` | `~/.claude/projects` | Where Claude Code stores sessions |
| `COPILOT_DIR` | `~/AppData/.../workspaceStorage` | Where Copilot stores memory files |
| `JWT_SECRET` | `change-me-in-production` | **Must be set to a strong random string in production** |
| `JWT_EXPIRE_HOURS` | `24` | How long JWT tokens stay valid |
| `API_HOST` | `127.0.0.1` | REST API bind host |
| `API_PORT` | `8000` | REST API port |
| `OPENAI_API_KEY` | — | Required for semantic search / embeddings |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI model used for embeddings |

---

## 7. The Knowledge Model

### What is a concept?

A concept is a structured knowledge page with these fields:

| Field | Type | Description |
|---|---|---|
| `title` | string | Brief descriptive name in Title Case |
| `type` | enum | Classification — see list below |
| `description` | string | One-line summary |
| `body` | markdown | Full content |
| `confidence` | `extracted` \| `inferred` | How sure we are |
| `visibility` | `workspace` \| `project` \| `private` | Who can see it |
| `tags` | list | Categorization keywords |
| `resource` | string | Source (e.g. `session:abc123`) |
| `embedding` | JSON | Float vector for semantic search (generated by `ichat embed`) |

### Concept types

| Type | Use for |
|---|---|
| `decision` | A design or architectural choice and the reasoning behind it |
| `solution` | A concrete fix to a specific problem |
| `pattern` | A recurring approach observed across multiple sessions |
| `tool` | A library, CLI tool, API, or service that was used |
| `concept` | A technical term or abstraction that needs definition |
| `project` | A named project or repository |
| `question` | An open question not yet answered |
| `error` | A specific error or failure mode that was encountered |
| `workaround` | A temporary fix while awaiting a better solution |
| `reference` | A link to an external document or spec |

### Relationship types

Concepts are connected by typed relationships:

| Type | Meaning |
|---|---|
| `uses` | A uses B |
| `solves` | A solves B (solution solves error) |
| `contradicts` | A and B conflict (triggers governance lint) |
| `depends_on` | A requires B |
| `related_to` | General association |
| `derived_from` | A was extracted from B |

---

## 8. Multi-User and Teams

### Roles

The platform supports two levels of membership:

**Workspace level** — applies to all projects:
- `owner` — full control, can manage members
- `editor` — can ingest, normalize, create concepts, run governance
- `viewer` — read-only access to workspace-visible content

**Project level** — overrides workspace role for a specific project:
- A workspace `viewer` can be promoted to `editor` on one project
- A contractor can be given project access without seeing everything

### Visibility

Concepts have a `visibility` field:
- `workspace` — visible to all workspace members
- `project` — visible only to members of that project
- `private` — visible to the creator only

The LLM decides whether new knowledge is workspace-wide (general pattern, reusable tool) or project-scoped (codebase-specific decision, project-specific workaround).

### Setting up a team workspace via API

```bash
# Start the API
ichat api

# Team member registers
curl -X POST http://localhost:8000/auth/register \
  -d '{"email":"teammate@example.com","name":"Alice","password":"...","workspace_name":"team-ws"}'

# Owner adds a member to their workspace
curl -X POST http://localhost:8000/workspaces/1/members \
  -H "Authorization: Bearer <owner-token>" \
  -d '{"email":"teammate@example.com","role":"editor"}'
```

### PostgreSQL for teams

For a shared team deployment, use PostgreSQL instead of SQLite:

```
DATABASE_URL=postgresql://user:password@host:5432/ichat
```

Run migrations:
```bash
python -m alembic upgrade head
```

---

## 9. Development Guide

### Run tests

```bash
pytest -q                          # all 80 tests
pytest tests/test_api.py -v        # one file, verbose
pytest -k "test_semantic"          # filter by name
```

### Lint

```bash
ruff check .                       # check
ruff check --fix --unsafe-fixes .  # auto-fix
```

### Add a database column

1. Edit `intelligent_chat/storage/models.py`
2. Generate migration: `python -m alembic revision --autogenerate -m "add xyz column"`
3. Review the generated file in `alembic/versions/`
4. Apply: `python -m alembic upgrade head`

**SQLite note:** When adding columns or FK constraints to existing SQLite tables, migrations must use batch mode:
```python
with op.batch_alter_table("concepts") as batch_op:
    batch_op.add_column(sa.Column("new_col", sa.Text(), nullable=True))
```

### Add a new LLM tool to the normalization prompt

Edit `intelligent_chat/normalization/prompts.py`. The normalization prompt uses Claude's tool-calling API — each knowledge action (`save_knowledge`, `link_concepts`) is a tool the LLM calls to structure its output.

### Test the MCP server locally

The MCP tools are regular Python functions — test them directly:

```python
from unittest.mock import patch
from intelligent_chat.mcp.server import search_knowledge

with patch("intelligent_chat.storage.database.get_session", return_value=my_test_session):
    result = search_knowledge(query="test query")
```

### Project structure decisions to preserve

- All config via `config.py` — never `os.getenv()` in feature code
- Tests use `StaticPool` for in-memory SQLite to avoid connection isolation issues
- Alembic batch mode required for all SQLite schema changes on existing tables
- Python must stay `< 3.13` (graph community detection library constraint)
