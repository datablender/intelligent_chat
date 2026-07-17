# Architecture Specification: Collective Memory Platform

## 1. Purpose

This document defines the technical architecture for a multi-user, open-source knowledge platform that ingests AI coding session transcripts, normalizes them into structured knowledge using an LLM, stores them in a relational database, and makes them searchable, graphable, and exportable in OKF format.

## 2. Design Principles

1. **LLM as active author** — normalization is not a parser; Claude reads raw transcripts and writes structured concept pages
2. **OKF as schema standard** — the Open Knowledge Format defines the shape of all knowledge records; the database stores OKF-structured data in relational form
3. **Database as canonical store** — PostgreSQL (or SQLite for local mode) is the source of truth; OKF markdown files are a derived export artifact
4. **Immutable raw archive** — source files are copied before any processing and never modified; the archive enables re-processing and auditing
5. **Multi-tenant from day one** — the schema includes workspace and user foreign keys on all records, even in single-user mode
6. **Portability** — OKF export is always lossless; the full knowledge base can be reconstructed from the export
7. **Separation of concerns** — ingestion, normalization, storage, search, graph, governance, and presentation are distinct layers with clean interfaces

## 3. Tech Stack

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.11 | Stable, below Leiden's < 3.13 constraint |
| Web framework | FastAPI | Async, auto-generated OpenAPI, good for API-first design |
| ORM | SQLAlchemy 2.0 | Async support, works with both PostgreSQL and SQLite |
| Migrations | Alembic | Pairs with SQLAlchemy, version-controlled schema changes |
| CLI | Typer | Python-native, built on Click, excellent DX |
| LLM | Anthropic SDK (Claude) | Normalization engine; claude-sonnet-5 for quality, haiku for speed |
| JSONL parsing | Adapted from claude-conversation-extractor | Battle-tested Base64 decode + transcript parse logic |
| Graph | Graphify (integration) | Leiden clustering, force-directed viz, MCP server, Obsidian export |
| Full-text search | PostgreSQL FTS / SQLite FTS5 | Built-in, no extra service for v1 |
| Package manager | uv | Fast, modern, isolated environments |
| Testing | pytest + pytest-asyncio | Async test support needed for FastAPI + SQLAlchemy |
| Linting | ruff | Fast, replaces flake8 + isort + black |

## 4. Layer Architecture

### 4.1 Ingestion Layer

Responsible for discovering and archiving raw source files.

**Connectors:**
- **Claude Code connector** — scans `~/.claude/projects/` for JSONL files; decodes Base64; extracts session metadata, messages, tool calls, token counts
- **Copilot connector** — scans VS Code workspace storage for memory-tool markdown files; parses YAML frontmatter and body
- **Manual connector** — accepts a path to a JSONL file or directory for one-off imports

**Raw archive:**
- Every source file is copied to `./archive/raw/{source_type}/{YYYY-MM-DD}/{session_id}.{ext}` before any processing
- Archive files are read-only after copy; never modified or deleted
- Archive preserves the original bytes exactly

**Hook integration:**
- Registers a Claude Code pre-compaction hook (`~/.claude/settings.json`) that triggers ingestion automatically when Claude Code archives a session
- Hook calls `ingestion ingest --source claude-code --session <id>`

**Output:** raw file path + parsed envelope (session id, source type, timestamps, token counts) passed to the normalization layer

### 4.2 Normalization Layer

Responsible for turning raw transcripts into OKF-structured knowledge records using Claude as the normalization engine.

**Process:**
1. Receive parsed transcript from ingestion layer
2. Build normalization prompt with the full transcript + current concept index (titles only, for context)
3. Call Claude API (claude-sonnet-5 or configurable model)
4. LLM returns a structured response specifying:
   - New concept pages to create (with full OKF fields + body)
   - Existing concept pages to update (diffs to apply)
   - Relationships to establish between concepts
   - Evidence snippets linking relationships to source passages
5. Write all records to the database in a single transaction

**OKF field mapping in the normalization prompt:**
- `type` — drawn from the canonical list in `conventions.md`
- `title` — human-readable, title-cased concept name
- `description` — one sentence summary
- `resource` — link to the source session record
- `tags` — drawn from the canonical tag taxonomy in `conventions.md`
- `confidence` — `extracted` (explicit in transcript) or `inferred` (relationship derived by LLM)

**conventions.md** — a file committed to the repo that defines:
- Canonical `type` values (e.g. `decision`, `solution`, `pattern`, `tool`, `project`, `question`, `concept`)
- Canonical tag taxonomy
- Naming conventions for concept titles
- Cross-linking rules

### 4.3 Storage Layer

The relational database is the canonical store. All records are multi-tenant from day one.

**Recommended deployment:**
- PostgreSQL — for multi-user team deployment
- SQLite — for local single-user mode; same schema, same ORM

**Core tables:**

```
users
  id, email, name, role, created_at

workspaces
  id, name, owner_id, visibility, created_at

workspace_members
  id, workspace_id, user_id, role (owner|editor|viewer), created_at

projects
  id, workspace_id, name, description, visibility (workspace|private), metadata

project_members
  id, project_id, user_id, role (owner|editor|viewer), created_at

sessions
  id, workspace_id, project_id, source_type, source_id,
  raw_archive_path, started_at, ended_at, token_count, status

messages
  id, session_id, role, content, timestamp,
  tool_name, token_count, metadata

concepts
  id, workspace_id, project_id (nullable), title, description, type, body,
  resource, confidence, visibility (workspace|project|private), created_at, updated_at

concept_tags
  concept_id, tag

relationships
  id, workspace_id, source_concept_id, target_concept_id,
  relation_type, confidence, evidence_id

evidence
  id, workspace_id, session_id, snippet, citation, created_at

governance_issues
  id, workspace_id, issue_type, severity, affected_entity_id,
  affected_entity_type, description, resolved, created_at

okf_export_log
  id, workspace_id, exported_at, export_path, record_count
```

**Concept scoping:**
- `project_id = NULL` — workspace-wide shared knowledge (general patterns, tools, language features)
- `project_id = X` — project-specific knowledge (decisions for this codebase, project-specific workarounds)
- The LLM normalization step decides scope via a `scope` field (`"workspace"` | `"project"`) in its tool output

**Relation types (edge vocabulary):**
`uses`, `imports`, `references`, `inherits`, `depends_on`,
`discusses`, `solves`, `contradicts`, `related_to`, `derived_from`,
`used_tool`, `mentioned_in`

**Confidence values:**
- `extracted` — relationship is explicit in the source transcript
- `inferred` — relationship was derived by the LLM from context

### 4.4 Search and Retrieval Layer

**Phase 1 — lexical:**
- PostgreSQL full-text search (tsvector + tsquery) over concept titles, bodies, and message content
- SQLite FTS5 for local mode
- Metadata filters: workspace, project, date range, type, tag, source type, confidence
- Results ranked by relevance with source citations

**Phase 2 — hybrid (post-MVP):**
- Embedding generation via Anthropic or OpenAI embeddings API
- pgvector extension for PostgreSQL vector storage
- Hybrid reranking combining lexical and semantic scores

**Phase 3 — semantic reasoning (long-term):**
- Concept retrieval with chain-of-thought reasoning
- Recommendation engine for knowledge gaps
- Question answering over indexed knowledge

### 4.5 Knowledge Graph Layer

**Graph construction:**
- Nodes: concepts, sessions, tools, projects, users
- Edges: `relationships` table records with type and confidence
- Graph is built from the database; exported as `graph.json` in Graphify-compatible format

**Graphify integration:**
- OKF export directory is passed to `graphify extract` for semantic extraction pass
- `graph.json` output consumed by Graphify's interactive HTML visualizer
- `graphify serve graph.json` exposes the graph as an MCP server for agent queries
- `graphify reflect` stores query outcomes in `graphify-out/memory/`

**Community detection:**
- Leiden algorithm partitions concept nodes into knowledge clusters
- Cluster labels optionally generated by LLM
- Requires Python < 3.13 (Leiden library constraint — enforced in pyproject.toml)

**God nodes:**
- Concepts with the highest edge count are surfaced as entry points in search and graph views
- Computed on export and stored in the graph manifest

**Graph outputs:**
- `graph.json` — Graphify-compatible, full node/edge data with confidence
- `graph.html` — self-contained interactive visualization (D3/Sigma.js via Graphify)
- GraphML — for import into Gephi or other graph tools
- Obsidian vault — wikilink-based markdown (identical to OKF export structure)

### 4.6 Governance Layer

Runs as a periodic job or on-demand CLI command. Produces `governance_issues` records for human review.

**Lint operations:**

| Check | What it detects | Severity |
|---|---|---|
| Contradiction | Two concept pages making conflicting claims about the same entity | high |
| Orphan | Concept with no incoming or outgoing relationships | medium |
| Staleness | Concept not updated while related sessions continued in the last N days | low |
| Broken link | Cross-reference in a concept body pointing to a non-existent concept | medium |
| Coverage gap | Topic appearing in 3+ sessions with no corresponding concept page | medium |
| Confidence drift | Inferred edges with no reinforcing evidence after N new sessions | low |

**Resolution workflow:**
- `governance lint` — run all checks, print findings
- `governance issues` — list open governance issues
- `governance resolve <id>` — mark an issue resolved with a note
- High-severity unresolved issues are flagged in the CLI on each run

### 4.7 Collaboration and Security Layer

Supports shared usage across teams. Schema is multi-tenant from day one; auth UI arrives post-MVP.

**Access control model:**

Two membership tables grant graduated access:

| Table | Scope | Roles |
|---|---|---|
| `workspace_members` | All projects in the workspace | `owner`, `editor`, `viewer` |
| `project_members` | A single project only | `owner`, `editor`, `viewer` |

Resolution rule: workspace role is the floor; a `project_members` row can promote a user's access on a specific project but never demote it. A workspace `viewer` can be a project `editor`. A user with no workspace membership cannot be granted project access.

**Visibility levels:**

| Level | Applies to | Who can see it |
|---|---|---|
| `workspace` | Projects, Concepts | All workspace members |
| `project` | Projects, Concepts | Project members only |
| `private` | Concepts | Concept owner only |

**Cross-project vs project-scoped knowledge:**
- `workspace` visibility concepts are shared across all projects — any project member can discover and reuse them
- `project` visibility concepts are siloed — only members of that specific project can see them
- This allows contractors to access their project without seeing unrelated work, while shared patterns remain discoverable

**Features:**
- User accounts with workspace and project-level roles
- Workspaces: named knowledge domains with an owner
- Permissions enforced at the service layer for all queries and writes
- Audit log: every create/update/delete on concepts and relationships recorded
- Change history: concept body diffs stored for review

### 4.8 Presentation Layer

**CLI (v1)** — primary interface:
```
ingest        Ingest a source directory or file
search        Search the knowledge base
export        Export OKF bundle or graph.json
governance    Run lint and manage issues
workspace     Manage workspaces
config        Show or update configuration
```

**TUI (post-MVP)** — terminal browsing of sessions and concepts

**Web UI (post-MVP)** — dashboard for search, graph exploration, workspace management

**MCP server (post-MVP)** — `graphify serve graph.json` for agent query access; REST API for programmatic access

**OKF export:**
- Generates a directory of markdown files with YAML frontmatter
- `index.md` — full concept catalog with one-line summaries grouped by type
- `log.md` — append-only chronological record of ingests, exports, and lint runs
- One `.md` file per concept, cross-linked by relative path
- Compatible with Graphify, Obsidian, GitHub rendering, and any markdown-aware tool

## 5. Data Flow

```
Source directory
  ↓
[Ingestion Layer] — discovers new files
  ↓ copies to
Raw archive (immutable, timestamped)
  ↓ parsed envelope
[Normalization Layer] — calls Claude API
  ↓ OKF-structured records
[Storage Layer] — PostgreSQL / SQLite
  ↓
[Search Layer] ←→ user queries
[Graph Layer] — builds graph.json from DB
[Governance Layer] — periodic lint over DB
[Presentation Layer] — CLI / TUI / web / MCP
  ↓ OKF export
Graphify / Obsidian / git archive
```

## 6. Deployment Model

| Mode | Storage | Use case |
|---|---|---|
| Local | SQLite | Single developer, zero infrastructure |
| Self-hosted | PostgreSQL | Team deployment, shared workspace |
| Cloud (future) | PostgreSQL + S3 | Larger teams, managed hosting |

## 7. Security and Privacy

- Local-first by default: all processing runs on local infrastructure
- No telemetry
- API keys stored in `.env`, never committed
- Secret redaction in normalization prompts: strip tokens, passwords, and keys from transcripts before sending to Claude API
- Role-based permissions enforced at the service layer — three roles (owner, editor, viewer) at both workspace and project level
- Project members cannot see workspace-level memberships or projects they are not members of
- Concept visibility (`workspace` | `project` | `private`) is enforced at query time, not just at write time
- Raw archive is local only and never transmitted

## 8. Integration Points

| Integration | How |
|---|---|
| Claude Code sessions | Pre-compaction hook + JSONL connector |
| Copilot sessions | Markdown connector over VS Code workspace storage |
| Graphify | OKF export directory → `graphify extract`; graph.json → Graphify viewer + MCP server |
| Obsidian | OKF export is structurally identical to an Obsidian vault |
| Git | OKF export committed as a standard git repo; Graphify's merge driver handles graph.json conflicts |
| Future MCP | Graphify MCP server wraps graph.json; REST API for programmatic access |
