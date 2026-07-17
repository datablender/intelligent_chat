import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# LLM — set one of ANTHROPIC_API_KEY or DEEPSEEK_API_KEY; LLM_PROVIDER auto-detects
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

def _default_provider() -> str:
    if DEEPSEEK_API_KEY:
        return "deepseek"
    return "anthropic"

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", _default_provider())
NORMALIZATION_MODEL: str = os.getenv(
    "NORMALIZATION_MODEL",
    "deepseek-chat" if LLM_PROVIDER == "deepseek" else "claude-sonnet-5",
)

# Database — defaults to local SQLite; set DATABASE_URL to a PostgreSQL URL for team mode
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ichat.db")

# Workspace — default workspace id for single-user mode
DEFAULT_WORKSPACE_ID: int = int(os.getenv("DEFAULT_WORKSPACE_ID", "1"))

# Archive — where raw source files are copied before processing
ARCHIVE_DIR: Path = Path(os.getenv("ARCHIVE_DIR", "./archive/raw"))

# API auth — set a strong random secret in production; never commit the real value
JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# API server
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# Semantic search — OpenAI embeddings
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Source directories
CLAUDE_CODE_DIR: Path = Path(os.getenv("CLAUDE_CODE_DIR", str(Path.home() / ".claude" / "projects")))
COPILOT_DIR: Path = Path(
    os.getenv(
        "COPILOT_DIR",
        str(
            Path.home()
            / "AppData"
            / "Roaming"
            / "Code"
            / "User"
            / "workspaceStorage"
        ),
    )
)
