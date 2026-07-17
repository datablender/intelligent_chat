next
# Product Specification: Collective Memory Platform for AI-Assisted Work

## 1. Product Summary

An open-source, multi-user knowledge platform that captures, organizes, and compounds knowledge from AI-assisted coding sessions. The system ingests raw transcripts from tools like Claude Code and GitHub Copilot, uses an LLM to normalize them into structured wiki pages, stores them in a shared relational database, and makes them searchable, graphable, and exportable.

The product is designed for teams who lose valuable knowledge between AI sessions and want a durable, shared memory layer that grows more useful over time.

## 2. Product Vision

Most AI-assisted work produces no lasting artifact. Conversations end, context is lost, and the same problems get solved repeatedly. This platform turns every AI session into a contribution to a shared knowledge base — one that compounds, stays searchable, and can be explored as a graph of connected ideas.

The long-term goal is a "hive brain" for technical teams: a living knowledge base that learns from every session, surfaces prior decisions, and reduces the cost of rediscovery.

## 3. Problem Statement

AI coding tools like Claude Code and GitHub Copilot generate valuable knowledge — solutions, decisions, tradeoffs, patterns — but that knowledge is:
- stored in proprietary, opaque formats
- trapped in individual sessions with no cross-session linking
- abandoned when the conversation ends
- inaccessible to teammates who weren't present

Teams repeat work, lose context, and fail to build on prior solutions. This platform solves that by treating every AI session as a knowledge contribution, not a throwaway conversation.

## 4. Target Audience

### Primary
- Solo developers using Claude Code or GitHub Copilot who want a searchable archive of their own work
- Technical teams who want shared memory across AI-assisted development workflows
- Engineering leads who need traceable decision history
- Researchers and knowledge workers who want durable, organized AI session archives

### Secondary
- Open-source contributors managing long-running projects
- Documentation teams who want to extract structured knowledge from AI sessions
- Organizations building internal AI knowledge systems

## 5. Core Operating Model

The platform is built around three first-class operations, drawn from Karpathy's LLM Wiki model:

### Ingest
When a new source is added or a session ends, the system:
1. Discovers new raw files in the configured source directory
2. Copies them to an immutable timestamped archive (never modified after copy)
3. Passes the raw transcript to an LLM (Claude)
4. The LLM reads the transcript and decides which concept pages to create or update
5. Normalized OKF-structured records are written to the database
6. Cross-links between concepts are established

The LLM is an active author in this step, not a parser. It decides what is worth preserving, how to frame it, and how it connects to existing knowledge.

### Query
Users ask questions against the knowledge base. The system searches across sessions, concepts, documents, and relationships, returns ranked results with source citations, and valuable query outputs can be promoted to new concept pages.

### Lint
A periodic or on-demand health check over the knowledge base that identifies:
- Contradictions between concept pages
- Orphan concepts with no incoming or outgoing relationships
- Stale content not updated while related sessions continued
- Broken cross-links between concept pages
- Coverage gaps — topics appearing frequently in sessions with no concept page
- Confidence drift — inferred relationships with no reinforcing evidence

Lint findings are surfaced for human review and resolution. This is what keeps the knowledge base from decaying.

## 6. Ingestion Sources

### v1
- **Claude Code** — JSONL transcript files from `~/.claude/projects/` (Base64-encoded); triggered automatically via pre-compaction hook or manual import
- **GitHub Copilot** — markdown files from Copilot memory tool storage in VS Code workspace storage

### Future
- Markdown documents and wikis
- Git repositories and commit history
- Issue trackers
- IDE session logs

## 7. Knowledge Representation

The platform uses the **Open Knowledge Format (OKF)** as its schema standard. OKF defines a concept document as a markdown file with YAML frontmatter carrying these fields:

```yaml
type: required — classification of this concept
title: human-readable name
description: one-line summary
resource: link to the source artifact
tags: categorization keywords
timestamp: last modification time
confidence: extracted | inferred
```

The body is free-form markdown with cross-links to other concepts using relative paths.

These fields map directly to columns in the relational database. The database is the canonical store for multi-user concurrent access. OKF markdown files are generated from the database on export — they are a derived artifact, not the source of truth. Because the schema mirrors OKF exactly, the export is always lossless.

A `conventions.md` schema document (committed to the repo) defines canonical `type` values, naming conventions, and tag taxonomy. This is what prevents the knowledge base from drifting into inconsistency.

**Concept scoping — two knowledge pools:**
- **Workspace-wide** (`project_id = NULL`): general patterns, tools, language features, reusable solutions — visible to all workspace members regardless of project
- **Project-scoped** (`project_id = X`): architectural decisions, project-specific workarounds, errors encountered in a particular codebase — visible only to members of that project

The LLM decides scope during normalization based on whether the knowledge is broadly reusable or tied to a specific codebase. The `visibility` field on each concept (`workspace` | `project` | `private`) further refines who can see it.

## 8. Product Scope

### In scope for v1 (MVP)
- Ingestion of Claude Code JSONL transcripts
- Ingestion of Copilot markdown memory files
- LLM-powered normalization into concept pages
- Immutable raw archive with timestamps
- PostgreSQL as the canonical store (SQLite for local/solo mode)
- Full-text search with metadata filters
- OKF bundle export (Markdown + YAML frontmatter)
- Graphify-compatible graph.json export
- Pre-compaction hook for automatic Claude Code capture
- Token tracking per session and message
- CLI interface

### In scope post-MVP
- Interactive graph visualization via Graphify
- Governance / Lint operations
- Multi-user workspaces and permissions
- Semantic and hybrid search
- TUI and web UI
- MCP server for agent integration
- Recommendation engine for knowledge gaps

### Out of scope for v1
- Enterprise SSO and compliance workflows
- Full autonomous agent orchestration
- Advanced multimodal ingestion (images, video)
- Large-scale SaaS deployment

## 9. Key Features

### 9.1 Zero-Friction Capture
Claude Code fires a pre-compaction hook when it archives a session. The platform wires into this hook so sessions are captured automatically without any user action. Manual import is also supported for backfills.

### 9.2 LLM-Powered Normalization
Raw transcripts are passed to Claude with a normalization prompt. The LLM identifies key concepts, decisions, tools used, files referenced, and relationships, then drafts or updates concept pages accordingly. One transcript may touch many concept pages.

### 9.3 Immutable Raw Archive
Every ingested source file is copied to a timestamped archive directory before any processing. The archive is never modified. It serves as the audit trail and allows re-processing with improved normalization prompts.

### 9.4 Structured Knowledge Store
Concepts, sessions, messages, relationships, and evidence are stored in PostgreSQL. Every record carries provenance (source session, timestamp, confidence). The schema is multi-tenant from day one even when running single-user.

### 9.5 Search and Retrieval
Full-text search across concepts, sessions, and messages. Metadata filters by project, date, tag, source type, and confidence. Ranked results with source citations.

### 9.6 Graph-Based Exploration
Knowledge relationships are exported as Graphify-compatible graph.json. Nodes are concepts, sessions, tools, projects, and users. Edges carry type and confidence. Leiden community detection groups related concepts into clusters. Highly-connected "god nodes" are surfaced as entry points. Interactive HTML visualization via Graphify.

### 9.7 OKF Export
The knowledge base can be exported at any time as an OKF bundle — a directory of markdown files with YAML frontmatter, cross-linked by relative path. This export is Graphify-compatible, human-readable, and importable into Obsidian. It is also suitable for git version control.

### 9.8 Access Control and Security

The platform supports both solo and team use with a two-level membership model:

**Workspace membership** — grants access to the entire workspace:
- `owner`: full control, can manage members and delete the workspace
- `editor`: can ingest sessions, create/update concepts, run governance
- `viewer`: read-only access to all workspace-visible content

**Project membership** — narrows or elevates access on a single project:
- A workspace `viewer` can be promoted to `editor` on one project
- A contractor can be given project access without workspace-wide visibility
- A user with no workspace membership cannot be granted project access

**Visibility levels applied at query time:**
- `workspace`: visible to all workspace members
- `project`: visible only to project members
- `private`: visible to the concept owner only

This means shared patterns and general knowledge compound across projects, while sensitive project-specific decisions stay scoped to the team that needs them.

### 9.9 Governance and Lint
Periodic health checks detect contradictions, orphan pages, stale knowledge, and coverage gaps. Findings are stored as structured records and surfaced in the CLI for review and resolution.

### 9.10 Token Tracking
Every ingested session records token counts per message and per session total. This data is used to rank session depth, identify high-value sessions for prioritized normalization, and provide usage analytics.

## 10. User Experience Principles

- **Zero friction to start** — the pre-compaction hook captures sessions automatically
- **Local and private by default** — all processing can run on local infrastructure; no telemetry
- **Transparent provenance** — every knowledge item shows where it came from and how confident the system is
- **Human in the loop** — the LLM drafts, humans review and correct; lint findings require human resolution
- **Portable** — knowledge is always exportable to open formats that work without this platform

## 11. Primary Workflow

1. Connect source directories (Claude Code, Copilot)
2. Sessions are captured automatically via hook or manual import
3. LLM normalizes sessions into concept pages
4. Knowledge base grows and cross-links over time
5. User searches or browses the knowledge base
6. Graph view reveals relationships and clusters
7. Lint keeps the knowledge base healthy
8. OKF export shares knowledge with tools, teammates, or archives

## 12. Success Criteria

The product is successful if:
- A developer can import their full Claude Code history and search it within minutes
- Relevant concept pages are found in under 3 seconds
- The LLM normalization step produces concept pages a developer would recognize as accurate
- Graph views surface relationships not obvious from reading individual sessions
- The knowledge base grows more useful over time rather than stagnating
- A team can share a knowledge base and find each other's work without coordination overhead
- The full knowledge base can be exported and used outside this platform

## 13. Positioning

This product sits at the intersection of:
- AI session archiving (what claude-code-log and claude-conversation-extractor do partially)
- LLM-maintained knowledge wikis (Karpathy's LLM Wiki model)
- Open knowledge formats (Google OKF standard)
- Graph-based knowledge exploration (Graphify)

It is not a transcript viewer. It is a platform that turns AI work sessions into compounding institutional memory.
