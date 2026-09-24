"""ChemSentry Database — SQLAlchemy ORM setup and session management (M4).

Connects to PostgreSQL and provides a database session for all API routes.
"""

import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from api.crypto import encrypt_existing_plaintext, validate_key_configuration

# Database URL from environment with fallback to SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chemsentry.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

try:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
except Exception:
    # Fallback to local SQLite if PostgreSQL connection fails
    DATABASE_URL = "sqlite:///./chemsentry.db"
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db() -> Session:
    """FastAPI dependency: Provide database session to routes.

    Usage:
        @app.get("/query")
        def query_route(db: Session = Depends(get_db)):
            result = db.query(SomeModel).first()
            return result
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database — create all tables from ORM models.

    Call this once on application startup to ensure schema exists.
    In production, use Alembic migrations instead.

    Also enforces encryption at rest (api/crypto.py): validates the data key
    up front so a missing/invalid production key fails at startup instead of on
    the first alert, then encrypts any plaintext rows left in an existing
    database from before encryption existed (idempotent, so safe to run on
    every start -- and this runs at import time too, see api/main.py).
    """
    validate_key_configuration()
    Base.metadata.create_all(bind=engine)
    encrypt_existing_plaintext(engine, Base.metadata)


def check_db_health() -> str:
    """Check if database is accessible.

    Returns:
        "ok" if connected, or error message
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            return "ok"
    except Exception as e:
        return f"error: {str(e)}"


def get_db_schema_info() -> dict:
    """Get information about database tables and columns (for debugging).

    Returns:
        {table_name: [column_names, ...], ...}
    """
    inspector = inspect(engine)
    schema = {}
    for table_name in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        schema[table_name] = columns
    return schema
