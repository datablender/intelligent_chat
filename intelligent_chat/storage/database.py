from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from intelligent_chat.config import DATABASE_URL
from intelligent_chat.storage.models import Base

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session() -> Session:
    return SessionLocal()


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
