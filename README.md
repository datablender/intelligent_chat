# iChat — Collective Memory Platform

Turn every AI coding session into compounding team knowledge.

iChat ingests transcripts from Claude Code and GitHub Copilot, uses an LLM to extract structured concept pages, and stores them in a searchable database. Teammates can search past sessions, explore the knowledge graph, and the MCP server makes that knowledge available to Claude Code during live sessions.

---

## Quick Start

```bash
# 1. Clone and install
git clone <repo>
cd intelligent_chat
python -m venv .venv && .venv/Scripts/activate  # Windows
pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# 3. Initialize
ichat init --name "my-workspace" --email "you@example.com"
python -m alembic upgrade head

# 4. Ingest your Claude Code history
ichat ingest scan

# 5. Normalize sessions into concept pages
ichat ingest normalize

# 6. Search
ichat search query "SQLAlchemy migrations"
```

For the full guide — setup, all commands, MCP integration, REST API, teams — see [docs/WIKI.md](docs/WIKI.md).

---

## What gets built

| Phase | Feature |
|---|---|
| Ingest | Claude Code + Copilot session import, LLM normalization, raw archive |
| Search | Full-text search with filters, semantic vector search |
| Export | OKF markdown bundle, Graphify-compatible graph.json |
| Governance | 6 lint checks (contradiction, orphan, staleness, broken links, gaps, drift) |
| API | FastAPI REST API with JWT auth, workspace/project membership |
| MCP | Claude Code tool integration — search the KB during live sessions |

## Requirements

- Python 3.11–3.12
- `ANTHROPIC_API_KEY` (for LLM normalization)
- `OPENAI_API_KEY` (optional, for semantic search)
- SQLite (default) or PostgreSQL

## License

MIT
