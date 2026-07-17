"""Claude Code connector — parses JSONL session files from ~/.claude/projects/."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from intelligent_chat.config import CLAUDE_CODE_DIR


def _parse_timestamp(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def _extract_content(content_blocks: list[dict]) -> tuple[str | None, str | None]:
    """Return (text_content, tool_name) from a message content block list."""
    text_parts: list[str] = []
    tool_name: str | None = None
    for block in content_blocks:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_name = block.get("name")
    return ("\n".join(text_parts) or None, tool_name)


def parse_session_file(path: Path) -> dict | None:
    """Parse a single Claude Code JSONL file into a session envelope.

    Returns None if the file contains no user/assistant messages.
    """
    session_id = path.stem
    messages: list[dict] = []
    started_at: datetime | None = None
    ended_at: datetime | None = None
    cwd: str | None = None
    git_branch: str | None = None
    total_output_tokens = 0

    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            record_type = record.get("type")
            if record_type not in ("user", "assistant"):
                continue

            ts = _parse_timestamp(record.get("timestamp"))
            if ts:
                if started_at is None or ts < started_at:
                    started_at = ts
                if ended_at is None or ts > ended_at:
                    ended_at = ts

            if cwd is None:
                cwd = record.get("cwd")
            if git_branch is None:
                git_branch = record.get("gitBranch")

            msg = record.get("message", {})
            role = msg.get("role", record_type)
            content_blocks = msg.get("content") or []
            text_content, tool_name = _extract_content(content_blocks)

            usage = msg.get("usage") or {}
            output_tokens: int = usage.get("output_tokens", 0)
            input_tokens: int = usage.get("input_tokens", 0)
            total_output_tokens += output_tokens

            messages.append({
                "uuid": record.get("uuid"),
                "role": role,
                "content": text_content,
                "timestamp": ts,
                "tool_name": tool_name,
                "token_count": output_tokens + input_tokens,
                "attrs": {
                    "usage": usage,
                    "model": msg.get("model"),
                    "stop_reason": msg.get("stop_reason"),
                } if record_type == "assistant" else None,
            })

    if not messages:
        return None

    project_name = Path(cwd).name if cwd else path.parent.name

    return {
        "session_id": session_id,
        "source_type": "claude_code",
        "project_name": project_name,
        "cwd": cwd,
        "git_branch": git_branch,
        "started_at": started_at,
        "ended_at": ended_at,
        "token_count": total_output_tokens,
        "messages": messages,
        "raw_path": path,
    }


def list_projects(claude_dir: Path = CLAUDE_CODE_DIR) -> list[dict]:
    """Return all Claude Code project slugs with session counts."""
    projects = []
    if not claude_dir.exists():
        return projects
    for entry in sorted(claude_dir.iterdir()):
        if entry.is_dir():
            jsonl_files = list(entry.glob("*.jsonl"))
            projects.append({"slug": entry.name, "sessions": len(jsonl_files), "path": entry})
    return projects


def find_project_dir(project: str, claude_dir: Path = CLAUDE_CODE_DIR) -> Path | None:
    """Find a project directory by slug, partial name, or real filesystem path.

    Matching order:
    1. Exact slug match (e.g. "c--Users-sujay-repos-myproject")
    2. Case-insensitive partial slug match (e.g. "myproject")
    3. Real path converted to slug (e.g. "C:\\Users\\sujay\\repos\\myproject")
    """
    if not claude_dir.exists():
        return None

    slug_lower = project.lower()

    # Try exact or partial slug match first
    candidates = [d for d in claude_dir.iterdir() if d.is_dir()]
    for d in candidates:
        if d.name.lower() == slug_lower:
            return d
    for d in candidates:
        if slug_lower in d.name.lower():
            return d

    # Try converting a real path to a slug
    try:
        encoded = Path(project).as_posix().lower().replace(":/", "--").replace("/", "-")
        for d in candidates:
            if d.name.lower() == encoded:
                return d
    except Exception:
        pass

    return None


def iter_sessions(claude_dir: Path = CLAUDE_CODE_DIR, project: str | None = None) -> Iterator[dict]:
    """Yield parsed session envelopes from JSONL files under claude_dir.

    If project is given, only sessions from that project directory are yielded.
    project can be a slug, partial name, or real filesystem path.
    """
    if project:
        project_dir = find_project_dir(project, claude_dir)
        if not project_dir:
            return
        search_root = project_dir
    else:
        search_root = claude_dir

    for jsonl_path in search_root.rglob("*.jsonl"):
        try:
            session = parse_session_file(jsonl_path)
            if session:
                yield session
        except Exception:
            continue


def get_session(session_id: str, claude_dir: Path = CLAUDE_CODE_DIR) -> dict | None:
    """Find and parse a single session by ID."""
    for jsonl_path in claude_dir.rglob(f"{session_id}.jsonl"):
        return parse_session_file(jsonl_path)
    return None
