"""Root pytest configuration and test environment isolation fixtures.

Problem this solves:
Previously, running pytest modified the developer's local `chemsentry.db` SQLite
database file because `api/database.py` constructs its SQLAlchemy engine at module
import time using the default DATABASE_URL ("sqlite:///./chemsentry.db").
This caused test runs to pollute local development state and leak test data
into the live development database.

Why this technique:
Pytest imports root `conftest.py` before collecting or importing any test modules.
By setting DATABASE_URL to a session-scoped temporary SQLite database here, any
subsequent import of `api.database` or `api.main` binds to this isolated test
database automatically. We also set a compliant 32-byte JWT secret key to prevent
PyJWT InsecureKeyLengthWarning during test runs and ensure deterministic auth.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

# Create an isolated temporary directory and database file for the test session
_TEST_DIR = tempfile.mkdtemp(prefix="chemsentry_test_db_")
_TEST_DB_PATH = Path(_TEST_DIR) / "test_chemsentry.db"

# Point DATABASE_URL at the temporary SQLite database before api.database is imported
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"

# Set a compliant 32-byte JWT secret key if not explicitly set in the environment
if not os.getenv("JWT_SECRET_KEY"):
    os.environ["JWT_SECRET_KEY"] = "chemsentry-test-suite-secret-key-32bytes-minimum!"

# Ensure CHEMSENTRY_ENV is development by default in tests unless explicitly overridden
if "CHEMSENTRY_ENV" not in os.environ:
    os.environ["CHEMSENTRY_ENV"] = "development"


def _cleanup_test_database() -> None:
    """Remove temporary test database directory on process exit.

    Problem this solves: Avoids leaving orphaned temporary database files across test runs.
    Why this technique: Registered with atexit to ensure execution even if pytest aborts.
    """
    try:
        shutil.rmtree(_TEST_DIR, ignore_errors=True)
    except Exception:
        pass


atexit.register(_cleanup_test_database)
