"""Tests for field-level encryption at rest (api/crypto.py, ADR 0004).

The unit tests use a throwaway in-memory SQLite database and an explicit random
key, so they can never touch (or be broken by) a developer's real chemsentry.db.
The last test deliberately uses the real app database, because the claim it
proves -- "a copied database file contains no readable alert data" -- is about
the real tables, not a model built for the test.
"""

import logging
import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

import api.crypto as crypto
import api.main as main
from api.crypto import (
    CIPHERTEXT_PREFIX,
    DATA_KEY_ENV_VAR,
    ENVIRONMENT_ENV_VAR,
    DecryptionError,
    EncryptedJSON,
    EncryptedText,
    EncryptionKeyError,
    decrypt_str,
    encrypt_existing_plaintext,
    encrypt_str,
)
from api.database import SessionLocal, engine
from api.db_models import AlertRecord, AuditLogRecord


@pytest.fixture
def fresh_key(monkeypatch, tmp_path):
    """Pin a random key for one test and restore the app's real key config after.

    Not autouse on purpose: the integration test at the bottom must run with
    the same key the shared app database was written with.
    """
    monkeypatch.setenv(DATA_KEY_ENV_VAR, Fernet.generate_key().decode())
    monkeypatch.delenv(ENVIRONMENT_ENV_VAR, raising=False)
    monkeypatch.setattr(crypto, "_DEV_KEY_FILE", tmp_path / "dev.key")
    crypto.reset_key_cache()
    yield
    crypto.reset_key_cache()


# --------------------------------------------------------------------------
# Core primitives
# --------------------------------------------------------------------------


def test_round_trip_and_ciphertext_hides_plaintext(fresh_key):
    secret = "Ethanol excursion in Zone_A at 40.0 °C — සුභ"
    stored = encrypt_str(secret)
    assert stored.startswith(CIPHERTEXT_PREFIX)
    assert "Ethanol" not in stored and "Zone_A" not in stored
    assert decrypt_str(stored) == secret


def test_same_plaintext_encrypts_differently_each_time(fresh_key):
    """A random IV per value means equal notes can't be spotted by comparing rows."""
    assert encrypt_str("approved") != encrypt_str("approved")


def test_tampered_value_is_rejected_not_returned_as_garbage(fresh_key):
    stored = encrypt_str("sign-off note")
    i = len(CIPHERTEXT_PREFIX) + 30
    tampered = stored[:i] + ("A" if stored[i] != "A" else "B") + stored[i + 1 :]
    with pytest.raises(DecryptionError):
        decrypt_str(tampered)


def test_wrong_key_is_rejected(fresh_key, monkeypatch):
    stored = encrypt_str("sign-off note")
    monkeypatch.setenv(DATA_KEY_ENV_VAR, Fernet.generate_key().decode())
    crypto.reset_key_cache()
    with pytest.raises(DecryptionError):
        decrypt_str(stored)


# --------------------------------------------------------------------------
# Key management
# --------------------------------------------------------------------------


def test_production_without_a_key_fails_closed_and_creates_no_dev_key(
    monkeypatch, tmp_path
):
    dev_key = tmp_path / "dev.key"
    monkeypatch.delenv(DATA_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")
    monkeypatch.setattr(crypto, "_DEV_KEY_FILE", dev_key)
    crypto.reset_key_cache()
    try:
        with pytest.raises(EncryptionKeyError):
            encrypt_str("x")
        with pytest.raises(EncryptionKeyError):
            crypto.validate_key_configuration()
        assert not dev_key.exists()
    finally:
        crypto.reset_key_cache()


def test_invalid_key_is_reported_clearly(monkeypatch):
    monkeypatch.setenv(DATA_KEY_ENV_VAR, "not-a-valid-fernet-key")
    crypto.reset_key_cache()
    try:
        with pytest.raises(EncryptionKeyError):
            encrypt_str("x")
    finally:
        crypto.reset_key_cache()


def test_dev_fallback_generates_a_key_once_and_reuses_it(monkeypatch, tmp_path):
    """Without a persisted key, alerts written before a restart would be
    unreadable after it -- so the dev key must survive a 'restart'."""
    dev_key = tmp_path / "dev.key"
    monkeypatch.delenv(DATA_KEY_ENV_VAR, raising=False)
    monkeypatch.delenv(ENVIRONMENT_ENV_VAR, raising=False)
    monkeypatch.setattr(crypto, "_DEV_KEY_FILE", dev_key)
    crypto.reset_key_cache()
    try:
        stored = encrypt_str("survives restart")
        assert dev_key.exists()
        crypto.reset_key_cache()  # simulate a process restart
        assert decrypt_str(stored) == "survives restart"
    finally:
        crypto.reset_key_cache()


def test_key_rotation_new_key_first_still_reads_old_rows(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    try:
        monkeypatch.setenv(DATA_KEY_ENV_VAR, old)
        crypto.reset_key_cache()
        old_row = encrypt_str("written under the old key")

        monkeypatch.setenv(DATA_KEY_ENV_VAR, f"{new},{old}")
        crypto.reset_key_cache()
        assert decrypt_str(old_row) == "written under the old key"
        new_row = encrypt_str("written under the new key")

        monkeypatch.setenv(DATA_KEY_ENV_VAR, old)  # new writes must not use old key
        crypto.reset_key_cache()
        with pytest.raises(DecryptionError):
            decrypt_str(new_row)

        monkeypatch.setenv(DATA_KEY_ENV_VAR, new)
        crypto.reset_key_cache()
        assert decrypt_str(new_row) == "written under the new key"
    finally:
        crypto.reset_key_cache()


# --------------------------------------------------------------------------
# SQLAlchemy column types + legacy migration (isolated in-memory database)
# --------------------------------------------------------------------------

_Base = declarative_base()


class _Note(_Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    body = Column(EncryptedText)
    meta = Column(EncryptedJSON)
    label = Column(String)


@pytest.fixture
def isolated_db(fresh_key):
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _Base.metadata.create_all(eng)
    yield eng, sessionmaker(bind=eng)
    eng.dispose()


def _raw(eng, column, row_id=1):
    with eng.connect() as conn:
        return conn.execute(
            text(f"SELECT {column} FROM notes WHERE id = :i"), {"i": row_id}
        ).scalar()


def test_columns_store_ciphertext_and_read_back_plaintext(isolated_db):
    eng, Session = isolated_db
    with Session() as s:
        s.add(
            _Note(
                id=1,
                body="reject: valve inspected °C",
                meta={"value": 40.0, "nested": {"ok": True}},
                label="visible",
            )
        )
        s.commit()

    assert _raw(eng, "body").startswith(CIPHERTEXT_PREFIX)
    assert "valve" not in _raw(eng, "body")
    assert _raw(eng, "meta").startswith(CIPHERTEXT_PREFIX)
    assert "40.0" not in _raw(eng, "meta")
    assert _raw(eng, "label") == "visible"  # non-sensitive columns stay queryable

    with Session() as s:
        note = s.get(_Note, 1)
        assert note.body == "reject: valve inspected °C"
        assert note.meta == {"value": 40.0, "nested": {"ok": True}}


def test_null_values_stay_null(isolated_db):
    eng, Session = isolated_db
    with Session() as s:
        s.add(_Note(id=1, body=None, meta=None))
        s.commit()
    assert _raw(eng, "body") is None
    with Session() as s:
        assert s.get(_Note, 1).body is None


def test_legacy_plaintext_rows_are_encrypted_in_place_and_idempotently(isolated_db):
    eng, Session = isolated_db
    with Session() as s:  # one row that is already encrypted, one NULL row
        s.add(_Note(id=2, body="already encrypted", meta={"k": 1}))
        s.add(_Note(id=3, body=None, meta=None))
        s.commit()
    already = (_raw(eng, "body", 2), _raw(eng, "meta", 2))
    with eng.begin() as conn:  # a pre-encryption row, written as raw plaintext
        conn.execute(
            text(
                "INSERT INTO notes (id, body, meta, label) "
                "VALUES (1, 'legacy secret', '{\"a\": 1}', 'x')"
            )
        )

    assert _raw(eng, "body") == "legacy secret"
    assert encrypt_existing_plaintext(eng, _Base.metadata) == 2  # body + meta

    assert _raw(eng, "body").startswith(CIPHERTEXT_PREFIX)
    assert "legacy" not in _raw(eng, "body")
    assert _raw(eng, "label") == "x"  # untouched
    assert (_raw(eng, "body", 2), _raw(eng, "meta", 2)) == already  # not re-encrypted
    with Session() as s:
        note = s.get(_Note, 1)
        assert note.body == "legacy secret" and note.meta == {"a": 1}

    assert encrypt_existing_plaintext(eng, _Base.metadata) == 0  # idempotent


def test_migration_leaves_no_plaintext_behind_in_the_sqlite_file(fresh_key, tmp_path):
    """An UPDATE alone leaves the old plaintext in freed pages (measured: 1184
    copies in the raw file for five 9 KB rows). The migration must VACUUM, so
    check the bytes on disk, not just what a SELECT returns."""
    path = tmp_path / "legacy.db"
    eng = create_engine(f"sqlite:///{path}")
    _Base.metadata.create_all(eng)
    with eng.begin() as conn:
        for i in range(1, 6):
            conn.execute(
                text("INSERT INTO notes (id, body) VALUES (:i, :b)"),
                {"i": i, "b": f"LEAKMARK{i}-" * 900},
            )
    assert path.read_bytes().count(b"LEAKMARK1-") > 0  # the premise: it starts readable

    assert encrypt_existing_plaintext(eng, _Base.metadata) == 5
    eng.dispose()

    on_disk = path.read_bytes()
    assert not any(f"LEAKMARK{i}-".encode() in on_disk for i in range(1, 6))


def test_reading_a_legacy_value_warns_once(fresh_key, caplog, monkeypatch):
    monkeypatch.setattr(crypto, "_legacy_warning_emitted", False)
    with caplog.at_level(logging.WARNING, logger="api.crypto"):
        assert decrypt_str("old plaintext") == "old plaintext"
        assert decrypt_str("more old plaintext") == "more old plaintext"
    assert sum("legacy" in r.getMessage() for r in caplog.records) == 1


# --------------------------------------------------------------------------
# Integration: the real app database
# --------------------------------------------------------------------------


def test_real_alert_tables_hold_only_ciphertext_but_the_api_still_reads_plaintext():
    """The actual security claim: someone who copies chemsentry.db reads nothing
    sensitive from alerts/audit_log, while the API (which holds the key) still
    returns everything in the clear."""
    alert_id = f"ALT_ENC_{uuid.uuid4().hex[:8]}"
    reasoning = f"SECRET-REASONING-{uuid.uuid4().hex}"
    notes = f"SECRET-NOTE-{uuid.uuid4().hex}"
    detail = f"SECRET-DETAIL-{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        db.add(
            AlertRecord(
                alert_id=alert_id,
                zone_id="Zone_A",
                chemical_name="Ethanol",
                current_value=40.0,
                unit="C",
                threshold_value=25.0,
                reasoning=reasoning,
                status="approved",
                created_by="analyst_user",
                created_at=now,
                signed_by="admin_user",
                notes=notes,
                signed_at=now,
            )
        )
        db.add(
            AuditLogRecord(
                action="sign_off",
                user_id="admin_user",
                resource=alert_id,
                details={"note": detail},
            )
        )
        db.commit()

        with engine.connect() as conn:
            alert_row = conn.execute(
                text(
                    "SELECT reasoning, notes, created_by, signed_by, zone_id "
                    "FROM alerts WHERE alert_id = :a"
                ),
                {"a": alert_id},
            ).one()
            audit_row = conn.execute(
                text("SELECT user_id, details FROM audit_log WHERE resource = :a"),
                {"a": alert_id},
            ).one()

        sensitive_values = list(alert_row[:4]) + list(audit_row)
        for value in sensitive_values:
            assert value.startswith(CIPHERTEXT_PREFIX)
        raw_dump = " ".join(sensitive_values)
        for secret in (reasoning, notes, detail, "analyst_user", "admin_user"):
            assert secret not in raw_dump
        assert alert_row[4] == "Zone_A"  # deliberately still plaintext / filterable

        client = TestClient(main.app)
        login = client.post(
            "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        served = next(
            a
            for a in client.get("/alerts", headers=headers).json()["alerts"]
            if a["alert_id"] == alert_id
        )
        assert served["reasoning"] == reasoning
        assert served["notes"] == notes
        assert served["created_by"] == "analyst_user"
        assert served["signed_by"] == "admin_user"
    finally:
        db.query(AuditLogRecord).filter(AuditLogRecord.resource == alert_id).delete()
        db.query(AlertRecord).filter(AlertRecord.alert_id == alert_id).delete()
        db.commit()
        db.close()
