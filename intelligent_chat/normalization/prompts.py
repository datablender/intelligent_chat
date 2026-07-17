"""Prompt templates and transcript formatting for the normalization pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_CONVENTIONS_PATH = Path(__file__).resolve().parent.parent.parent / "conventions.md"


def load_conventions() -> str:
    """Load the OKF conventions document used in normalization prompts."""
    if _CONVENTIONS_PATH.exists():
        return _CONVENTIONS_PATH.read_text(encoding="utf-8")
    return ""


def format_transcript(messages: list[dict]) -> str:
    """Format a list of message dicts into a readable transcript string."""
    lines: list[str] = []
    for msg in messages:
        ts: datetime | None = msg.get("timestamp")
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "unknown time"
        role = msg.get("role", "unknown").upper()
        content = msg.get("content") or ""
        tool = msg.get("tool_name")

        lines.append(f"[{ts_str}] {role}:")
        if content:
            lines.append(content)
        if tool:
            lines.append(f"[Tool used: {tool}]")
        lines.append("")

    return "\n".join(lines)


def build_system_prompt(conventions: str) -> str:
    return f"""You are a knowledge extraction agent. Your job is to read AI coding session transcripts and extract durable knowledge into structured concept pages.

You must call the `save_knowledge` tool with every concept and relationship you find. Do not respond with plain text — always call the tool.

EXTRACTION RULES:
- Extract only knowledge that is genuinely useful to revisit: decisions, solutions, patterns, tools, concepts, errors, workarounds
- Skip small talk, routine commands, and ephemeral details
- One session may produce many concept pages, or just one, or none — use judgment
- When a concept clearly already exists (listed in the concept index), use action "update" and provide the existing_id
- Cross-link concepts using their exact titles

SCOPING RULES (determines who can see a concept):
- scope "workspace": general knowledge reusable across any project — patterns, tools, language features, generic solutions
- scope "project": knowledge tied to THIS project's context — architectural decisions for this codebase, project-specific workarounds, errors in this project's stack, configurations specific to this repo
- When in doubt, prefer "workspace" so knowledge is shared broadly

OKF CONVENTIONS (you must follow these exactly):
{conventions}
"""


def build_user_prompt(
    transcript: str,
    project_name: str,
    session_id: str,
    concept_index: list[dict],
) -> str:
    index_lines = "\n".join(
        f"  id={c['id']} | type={c['type']} | title={c['title']} | {c['description'] or ''}"
        for c in concept_index
    ) or "  (no existing concepts yet)"

    return f"""PROJECT: {project_name}
SESSION ID: {session_id}

EXISTING CONCEPT INDEX:
{index_lines}

TRANSCRIPT:
{transcript}

Extract all durable knowledge from this transcript. Call `save_knowledge` now."""


SAVE_KNOWLEDGE_TOOL = {
    "name": "save_knowledge",
    "description": "Save extracted knowledge concepts and relationships from the transcript.",
    "input_schema": {
        "type": "object",
        "properties": {
            "concepts": {
                "type": "array",
                "description": "Concept pages to create or update.",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "update"],
                            "description": "create for new concepts, update for existing ones",
                        },
                        "existing_id": {
                            "type": "integer",
                            "description": "Required when action is update — the concept id from the index",
                        },
                        "title": {"type": "string"},
                        "type": {
                            "type": "string",
                            "description": "Must be one of the canonical types from conventions.md",
                        },
                        "description": {
                            "type": "string",
                            "description": "One sentence summary",
                        },
                        "body": {
                            "type": "string",
                            "description": "Full markdown body of the concept page",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags from the canonical taxonomy",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["extracted", "inferred"],
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["workspace", "project"],
                            "description": "workspace = reusable across all projects; project = specific to this project's codebase",
                        },
                    },
                    "required": ["action", "title", "type", "description", "body", "tags", "confidence", "scope"],
                },
            },
            "relationships": {
                "type": "array",
                "description": "Relationships between concepts.",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_title": {"type": "string"},
                        "target_title": {"type": "string"},
                        "relation_type": {
                            "type": "string",
                            "description": "Must be one of the canonical relation types from conventions.md",
                        },
                        "confidence": {"type": "string", "enum": ["extracted", "inferred"]},
                        "evidence_snippet": {
                            "type": "string",
                            "description": "Optional short quote from the transcript supporting this relationship",
                        },
                    },
                    "required": ["source_title", "target_title", "relation_type", "confidence"],
                },
            },
        },
        "required": ["concepts", "relationships"],
    },
}
