"""OKF exporter — generates markdown + YAML frontmatter bundle from the database."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from intelligent_chat.storage.models import Concept, OKFExportLog


def _safe_filename(title: str) -> str:
    """Convert a concept title to a safe lowercase filename."""
    name = title.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    return name[:80] + ".md"


def _render_concept(concept: Concept, all_titles: set[str]) -> str:
    """Render a concept as an OKF markdown file with YAML frontmatter."""
    tags_yaml = "\n".join(f"  - {t.tag}" for t in concept.tags) or "  []"
    resource = concept.resource or ""
    updated = concept.updated_at.isoformat() if concept.updated_at else ""
    project_line = f"project_id: {concept.project_id}\n" if concept.project_id else ""

    frontmatter = (
        f"---\n"
        f"type: {concept.type}\n"
        f"title: {concept.title}\n"
        f"description: >\n  {concept.description or ''}\n"
        f"resource: {resource}\n"
        f"tags:\n{tags_yaml}\n"
        f"timestamp: {updated}\n"
        f"confidence: {concept.confidence}\n"
        f"visibility: {concept.visibility}\n"
        f"{project_line}"
        f"---\n\n"
    )

    body = concept.body or ""

    # Convert mentions of other concept titles to relative markdown links
    for title in sorted(all_titles, key=len, reverse=True):
        if title == concept.title:
            continue
        link_text = f"[{title}]({_safe_filename(title)})"
        # Only replace whole-word occurrences not already inside a link
        body = re.sub(
            rf"(?<!\[)(?<!\()(?<!\w){re.escape(title)}(?!\w)(?!\])",
            link_text,
            body,
        )

    return frontmatter + body + "\n"


def _render_index(concepts: list[Concept]) -> str:
    """Render index.md grouped by concept type."""
    by_type: dict[str, list[Concept]] = {}
    for c in concepts:
        by_type.setdefault(c.type, []).append(c)

    lines = ["# Knowledge Base Index\n"]
    for ctype in sorted(by_type):
        lines.append(f"\n## {ctype.title()}\n")
        for c in sorted(by_type[ctype], key=lambda x: x.title):
            filename = _safe_filename(c.title)
            desc = f" — {c.description}" if c.description else ""
            lines.append(f"- [{c.title}]({filename}){desc}")

    return "\n".join(lines) + "\n"


def _append_log(log_path: Path, event: str) -> None:
    """Append a timestamped line to log.md."""
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"- {ts} — {event}\n")


def export_okf(
    db: Session,
    workspace_id: int,
    output_dir: Path,
    *,
    project_ids: list[int] | None = None,
) -> dict:
    """Export all accessible concepts to an OKF markdown bundle.

    project_ids restricts export to workspace-visible + listed project concepts.
    When None, exports all workspace concepts (admin / single-user mode).

    Returns: {exported: int, output_dir: str}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "log.md"

    q = db.query(Concept).filter(Concept.workspace_id == workspace_id)
    if project_ids is not None:
        from sqlalchemy import or_
        q = q.filter(
            or_(
                Concept.visibility == "workspace",
                Concept.project_id.in_(project_ids),
            )
        )
    concepts = q.order_by(Concept.title).all()

    all_titles = {c.title for c in concepts}
    exported = 0

    for concept in concepts:
        filename = _safe_filename(concept.title)
        content = _render_concept(concept, all_titles)
        (output_dir / filename).write_text(content, encoding="utf-8")
        exported += 1

    # index.md
    (output_dir / "index.md").write_text(_render_index(concepts), encoding="utf-8")

    # log.md
    _append_log(log_path, f"export okf — {exported} concepts → {output_dir}")

    # Record in DB
    db.add(OKFExportLog(
        workspace_id=workspace_id,
        export_path=str(output_dir),
        record_count=exported,
    ))
    db.commit()

    return {"exported": exported, "output_dir": str(output_dir)}
