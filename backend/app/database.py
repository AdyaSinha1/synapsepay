"""SQLAlchemy 2.x engine/session setup.

DATABASE_URL picks the database: default is a local SQLite file for dev and
tests; production points at Postgres (Neon/Supabase/Render). The repository
layer in db.py keeps the existing business logic untouched.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    url = (config.DATABASE_URL or "").strip() or "sqlite:///./synapsepay.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def make_engine(url: str | None = None):
    resolved = url or _database_url()
    kwargs = {}
    if _is_sqlite(resolved):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
    return create_engine(resolved, pool_pre_ping=True, future=True, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
