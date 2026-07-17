import shutil
from datetime import UTC, datetime
from pathlib import Path

from intelligent_chat.config import ARCHIVE_DIR


def archive_file(source_path: Path, source_type: str, session_id: str) -> Path:
    """Copy source file to immutable timestamped archive. Returns the archive path.

    Files are stored at: ARCHIVE_DIR/{source_type}/{YYYY-MM-DD}/{session_id}{ext}
    Already-archived files are not overwritten (idempotent).
    """
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    suffix = source_path.suffix or ".jsonl"
    dest_dir = ARCHIVE_DIR / source_type / date_str
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{session_id}{suffix}"

    if not dest.exists():
        shutil.copy2(source_path, dest)
        dest.chmod(0o444)  # read-only after copy

    return dest
