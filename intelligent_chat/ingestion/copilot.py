"""Copilot connector — reads Copilot memory-tool markdown files from VS Code workspace storage."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from intelligent_chat.config import COPILOT_DIR

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_YAML_FIELD_RE = re.compile(r"^(\w[\w-]*):\s*(.+)$", re.MULTILINE)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (fields dict, body) from a markdown document."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_yaml = match.group(1)
    fields = dict(_YAML_FIELD_RE.findall(raw_yaml))
    body = text[match.end():]
    return fields, body


def parse_copilot_file(path: Path) -> dict | None:
    """Parse a single Copilot memory markdown file into a document envelope."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if not text.strip():
        return None

    fields, body = _parse_frontmatter(text)
    title = fields.get("name") or fields.get("title") or path.stem
    description = fields.get("description", "")

    # Use file modification time as the timestamp
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    # Derive workspace hash from grandparent directory name (the UUID-like hash)
    workspace_hash = path.parent.name

    return {
        "session_id": f"copilot_{workspace_hash}_{path.stem}",
        "source_type": "copilot",
        "project_name": workspace_hash,
        "title": title,
        "description": description,
        "body": body.strip(),
        "fields": fields,
        "timestamp": mtime,
        "raw_path": path,
    }


def iter_sessions(copilot_dir: Path = COPILOT_DIR) -> Iterator[dict]:
    """Yield parsed document envelopes from Copilot memory-tool markdown files."""
    for md_path in copilot_dir.rglob("*.md"):
        if "memory-tool" not in str(md_path).replace("\\", "/"):
            continue
        try:
            doc = parse_copilot_file(md_path)
            if doc:
                yield doc
        except Exception:
            continue
