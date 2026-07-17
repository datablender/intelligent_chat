# OKF Conventions

This document defines the canonical schema for all knowledge records in this platform.
The LLM normalization pipeline uses this document as part of its system prompt.
All concept pages must conform to these conventions.

---

## Concept Types (`type` field)

Every concept page must have exactly one type from this list.

| Type | What it represents |
|---|---|
| `decision` | A design or architectural choice made during a session — what was chosen and why |
| `solution` | A concrete fix or answer to a specific problem |
| `pattern` | A recurring approach, technique, or structure observed across multiple sessions |
| `tool` | A CLI tool, library, API, or external service used in the work |
| `concept` | A technical concept, term, or abstraction that needs definition |
| `project` | A named project, repository, or product being worked on |
| `question` | An open question or area of uncertainty that hasn't been resolved |
| `error` | A specific error, exception, or failure mode that was encountered |
| `workaround` | A temporary or suboptimal fix applied while awaiting a better solution |
| `reference` | A link to an external document, spec, repository, or resource |

---

## Confidence Values (`confidence` field)

| Value | Meaning |
|---|---|
| `extracted` | This relationship or claim is explicitly stated in the source transcript |
| `inferred` | This relationship or claim was derived by the LLM from context; not directly stated |

Default to `extracted`. Use `inferred` only when the LLM is synthesizing across multiple sources.

---

## Tag Taxonomy (`tags` field)

Tags are comma-separated keywords. Use tags from the canonical lists below.
Multiple categories may apply to a single concept.

### Language / Runtime
`python`, `javascript`, `typescript`, `go`, `rust`, `sql`, `bash`, `html`, `css`

### Domain
`api`, `cli`, `database`, `frontend`, `backend`, `devops`, `testing`, `security`,
`performance`, `data-pipeline`, `llm`, `graph`, `search`, `auth`, `storage`

### Status
`active`, `deprecated`, `experimental`, `stable`, `open`, `resolved`

### Source
`claude-code`, `copilot`, `manual`

---

## Naming Rules

- Titles use **Title Case**: `SQLAlchemy Migration Strategy`, not `sqlalchemy migration strategy`
- Be specific: `Alembic Autogenerate with SQLite` not `Database Migration`
- Tools are named exactly as they appear: `FastAPI`, `Typer`, `SQLAlchemy`
- Avoid verbs in titles; prefer noun phrases: `Token Counting Approach` not `How We Count Tokens`

---

## Body Format

Concept body is free-form markdown. Recommended structure:

```markdown
Brief one-paragraph summary of the concept.

## Context
Why this concept is relevant to the project.

## Details
The substance of the knowledge: how it works, what was decided, what the solution is.

## Notes
Edge cases, caveats, or things to watch out for.
```

Cross-link to related concepts using relative paths: `[Related Concept](../concept/related-concept.md)`

---

## Reserved Filenames

| File | Purpose |
|---|---|
| `index.md` | Full concept catalog grouped by type, one-line summaries |
| `log.md` | Append-only chronological record of ingests, exports, and governance runs |
| `conventions.md` | This file — the schema doc |

---

## Relationship Types

Use these edge labels when establishing relationships between concepts.

| Type | Direction | Example |
|---|---|---|
| `uses` | A uses B | `FastAPI` uses `Pydantic` |
| `imports` | A imports B | `pipeline.py` imports `Anthropic SDK` |
| `references` | A references B | `decision` references `spec doc` |
| `inherits` | A inherits B | `AdminUser` inherits `User` |
| `depends_on` | A depends on B | `search` depends_on `storage` |
| `discusses` | session discusses concept | session discusses `OKF Format` |
| `solves` | A solves B | `solution` solves `error` |
| `contradicts` | A contradicts B | two decisions that conflict |
| `related_to` | A is related to B | general association |
| `derived_from` | A derived from B | concept extracted from session |
| `used_tool` | session used tool | session used `Alembic` |
| `mentioned_in` | concept mentioned in session | concept mentioned_in session |
