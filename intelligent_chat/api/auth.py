"""JWT utilities — token creation and verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from intelligent_chat.config import JWT_ALGORITHM, JWT_EXPIRE_HOURS, JWT_SECRET


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Decode a JWT and return the user_id (sub). Raises jwt.PyJWTError on failure."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])
