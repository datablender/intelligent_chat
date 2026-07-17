# Backlog

## Shipped

- [x] Project scaffold, SQLAlchemy models (14 tables), Alembic migrations
- [x] Claude Code connector (JSONL + Base64 decode)
- [x] Copilot connector (Markdown memory files)
- [x] Raw archive writer (immutable timestamped copies)
- [x] LLM normalization pipeline (Claude tool-calling → concept pages)
- [x] Dual-scope knowledge: workspace-wide (`project_id = NULL`) and project-scoped
- [x] Full-text search with metadata filters (type, tag, project, date range)
- [x] OKF Markdown bundle export with YAML frontmatter + cross-links + index
- [x] Graphify-compatible graph.json export
- [x] Governance lint: 6 checks (contradiction, orphan, staleness, broken_link, coverage_gap, confidence_drift)
- [x] FastAPI REST API with JWT auth (register, login, me)
- [x] Workspace + project membership (owner / editor / viewer roles)
- [x] Permission-aware concepts API (visibility enforcement)
- [x] AuditLog (append-only record of all writes)
- [x] Semantic search: OpenAI embeddings + cosine similarity
- [x] `ichat embed` — bulk embedding generation
- [x] MCP server (FastMCP) with 5 tools: search_knowledge, semantic_search, get_concept, list_recent, save_note
- [x] `.mcp.json` for Claude Code auto-detection
- [x] Full documentation (README, WIKI, CLAUDE.md)

## Up Next

### Hybrid Search
Combine keyword score + cosine similarity into a single ranked result list. Currently they're separate modes. A hybrid ranker would let you run one query and get the best of both.

### Web UI
A minimal frontend on top of the existing FastAPI. The API is fully built — a simple React or HTMX interface would make the knowledge base accessible without the CLI.
- Concept browser (search, filter, read)
- Graph view (embed Graphify iframe or build simple D3 viz)
- Workspace management

### Docker Compose Deployment
A `docker-compose.yml` for:
- PostgreSQL database
- iChat API server
- Optional: pgvector extension for proper vector indexing

One-command team deployment.

### pgvector Integration
The current semantic search loads all embeddings into Python for cosine similarity. For workspaces with thousands of concepts, proper pgvector kNN indexing would be much faster. Needs:
- Optional `pgvector` package
- `Vector` column type on PostgreSQL
- `<=>` operator in the search query

### Re-embed on Concept Update
When a concept's body or description changes, its embedding goes stale. An auto-embed trigger (or a flag in the pipeline) would keep embeddings fresh without a full `ichat embed --force`.

### Concept Diff History
Store diffs when a concept is updated so changes are reviewable. The AuditLog records that a change happened; the diff history records what changed.

### Invite Flow
Email-based team invite for the API. Currently you add members by email (they must already have an account). A proper invite would send a sign-up link.

### Recommendation Engine
Given a concept, surface related concepts with no direct relationship — potential knowledge connections the LLM missed. Useful for building a denser knowledge graph over time.

### Graphify Live Integration
`ichat graph serve` — run Graphify against the live graph.json for interactive exploration. Currently the graph.json is static; a live mode would update as new sessions are normalized.
