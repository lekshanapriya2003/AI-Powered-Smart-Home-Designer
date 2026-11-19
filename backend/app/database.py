"""database.py - SQLAlchemy engine, session factory and the declarative Base."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# pool_pre_ping drops dead connections, e.g. after Postgres restarts during dev.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """All ORM models inherit from this."""


def get_db():
    """FastAPI dependency: give each request its own session and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
