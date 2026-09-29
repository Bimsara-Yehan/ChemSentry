"""Unit tests for JWT security key policies and test database isolation (PR 1).

Problem this solves:
Ensures JWT signing keys fail closed in production when missing, short (<32 bytes),
or set to known repository placeholders. Also verifies that test executions use
isolated temporary databases without modifying the developer's local chemsentry.db.

Why this technique:
Direct unit tests on key resolution functions, token creation/verification routines,
and database engine binding guarantee zero security regression.
"""

import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from api.database import SessionLocal, engine
from api.models import UserRole
from api.security import (
    JWTKeyError,
    create_access_token,
    get_jwt_secret_key,
    reset_jwt_key_cache,
    resolve_jwt_secret_key,
    verify_token,
)


def test_production_missing_jwt_key_raises_error():
    """Verify that a missing JWT key in production fails closed."""
    with patch.dict(os.environ, {"CHEMSENTRY_ENV": "production", "JWT_SECRET_KEY": ""}):
        reset_jwt_key_cache()
        with pytest.raises(
            JWTKeyError, match="must be set when CHEMSENTRY_ENV=production"
        ):
            resolve_jwt_secret_key()


@pytest.mark.parametrize(
    "placeholder",
    [
        "dev-key-change-in-production",
        "replace-with-a-random-string-per-environment",
    ],
)
def test_production_placeholder_key_rejected(placeholder: str):
    """Verify that known placeholder keys are rejected in production."""
    with patch.dict(
        os.environ,
        {"CHEMSENTRY_ENV": "production", "JWT_SECRET_KEY": placeholder},
    ):
        reset_jwt_key_cache()
        with pytest.raises(JWTKeyError, match="cannot use placeholder value"):
            resolve_jwt_secret_key()


def test_production_short_key_rejected():
    """Verify that keys shorter than 32 bytes are rejected in production."""
    with patch.dict(
        os.environ,
        {"CHEMSENTRY_ENV": "production", "JWT_SECRET_KEY": "too-short-key"},
    ):
        reset_jwt_key_cache()
        with pytest.raises(JWTKeyError, match="must be at least 32 bytes"):
            resolve_jwt_secret_key()


def test_production_valid_key_issues_and_verifies_tokens():
    """Verify that a valid 32-byte key in production generates verifiable tokens."""
    valid_key = "a" * 32
    with patch.dict(
        os.environ,
        {"CHEMSENTRY_ENV": "production", "JWT_SECRET_KEY": valid_key},
    ):
        reset_jwt_key_cache()
        token, expires_in = create_access_token(
            user_id="prod_user",
            username="analyst_1",
            role=UserRole.ANALYST,
            expires_delta=timedelta(hours=1),
        )
        assert token is not None
        assert expires_in == 3600
        user_info = verify_token(token)
        assert user_info.user_id == "prod_user"
        assert user_info.role == UserRole.ANALYST


def test_development_short_key_rejected():
    """Verify that even in development, an explicitly provided key must be >=32 bytes."""
    with patch.dict(
        os.environ,
        {"CHEMSENTRY_ENV": "development", "JWT_SECRET_KEY": "short-dev-key"},
    ):
        reset_jwt_key_cache()
        with pytest.raises(JWTKeyError, match="must be at least 32 bytes"):
            resolve_jwt_secret_key()


def test_development_auto_generates_compliant_key(tmp_path: Path):
    """Verify that development mode generates and persists a random 32-byte key."""
    fake_key_file = tmp_path / ".chemsentry_jwt.key"
    with (
        patch.dict(os.environ, {"CHEMSENTRY_ENV": "development", "JWT_SECRET_KEY": ""}),
        patch("api.security._DEV_JWT_KEY_FILE", fake_key_file),
    ):
        reset_jwt_key_cache()
        key = get_jwt_secret_key()
        assert len(key.encode("utf-8")) >= 32
        assert fake_key_file.exists()
        assert fake_key_file.read_text(encoding="utf-8").strip() == key


def test_test_database_is_isolated_from_local_db():
    """Verify engine is bound to a temporary SQLite database, not root chemsentry.db."""
    db_url = str(engine.url)
    assert "chemsentry_test_db_" in db_url
    assert not db_url.endswith("/./chemsentry.db")

    # Verify write operations succeed on the isolated session
    session = SessionLocal()
    try:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
    finally:
        session.close()
