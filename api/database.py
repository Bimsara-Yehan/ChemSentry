"""ChemSentry Database — SQLAlchemy ORM setup and session management (M4).

Connects to PostgreSQL and provides a database session for all API routes.
"""

import os
import socket

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


def check_mqtt_broker_health(timeout_seconds: float = 2.0) -> str:
    """Check if the MQTT broker's TLS port is actually reachable.

    Problem this solves: GET /health previously hardcoded mqtt_broker to "ok"
    unconditionally -- the same kind of fake status the UI's "System Online"
    badge had, just one layer down. A bare TCP connect attempt (no TLS
    handshake, no MQTT CONNECT) is enough to prove "something is listening on
    this port" without this process needing to hold a persistent MQTT client
    or a device certificate just to answer a health check.

    Why a raw socket connect and not a real MQTT client: a full paho-mqtt
    client needs a client cert (mutual TLS, mosquitto.conf's
    require_certificate true) and would need to stay connected or reconnect
    on every health check -- real cost and real complexity for a check whose
    only job is "is the broker process up and accepting connections."
    """
    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "8883"))
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return "ok"
    except OSError as e:
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
