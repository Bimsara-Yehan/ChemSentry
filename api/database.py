"""ChemSentry Database — SQLAlchemy ORM setup and session management (M4).

Connects to PostgreSQL and provides a database session for all API routes.
"""

import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://chemsentry:localdev@localhost:5432/chemsentry"
)

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    pool_pre_ping=True,  # Verify connections before using
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
    """
    Base.metadata.create_all(bind=engine)


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
