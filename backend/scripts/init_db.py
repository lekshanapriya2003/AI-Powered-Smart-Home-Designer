"""init_db.py - creates the database (if missing) and all tables.

Run from the backend folder:  python scripts/init_db.py
Safe to run again: existing tables are left untouched.
"""
import sys
from pathlib import Path

# Make "import app..." work when this file is run directly as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL
from app import models  # noqa: F401  (importing registers the tables on Base)
from app.database import Base, engine


def create_database_if_missing() -> None:
    """Create the target database by connecting to the default 'postgres' one."""
    url = make_url(DATABASE_URL)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        ).scalar()
        if not exists:
            # CREATE DATABASE cannot use bind parameters, so quote the name ourselves.
            safe_name = url.database.replace('"', '""')
            conn.execute(text(f'CREATE DATABASE "{safe_name}"'))
            print(f"Created database '{url.database}'")
    admin_engine.dispose()


def add_missing_columns() -> None:
    """Add columns introduced after Phase 1 to an existing database (create_all never alters tables)."""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE design_requests ADD COLUMN IF NOT EXISTS parent_request_id INTEGER "
            "REFERENCES design_requests(id) ON DELETE SET NULL"
        ))


def main() -> None:
    """Create the database and tables, then print what exists."""
    try:
        create_database_if_missing()
        Base.metadata.create_all(engine)
        add_missing_columns()
    except OperationalError as exc:
        print("Could not connect to PostgreSQL. Is it running, and is DATABASE_URL correct?")
        print(f"Details: {exc.orig}")
        sys.exit(1)

    tables = inspect(engine).get_table_names()
    print("Tables ready:", ", ".join(sorted(tables)))


if __name__ == "__main__":
    main()
