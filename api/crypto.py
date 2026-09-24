"""ChemSentry field-level encryption at rest (M4).

Problem this solves: `chemsentry.db` (SQLite) or a Postgres dump is a plain file.
Anyone who copies it -- a laptop backup, a leaked dump, a stolen disk -- can read
every alert narrative, every sign-off note and every "who did what" audit entry.
This module encrypts those columns transparently at the ORM boundary, so route
code in `api/main.py` reads and writes plain Python values and never touches a key.

Why field-level Fernet rather than SQLCipher / whole-file encryption: SQLCipher
needs a platform-specific native build (painful on the team's Windows machines and
CI), and it protects only the SQLite path -- the same code must work unchanged
against PostgreSQL, where the equivalent is disk/volume encryption at deployment.
Field-level encryption is portable, testable in plain pytest, and protects the
data-in-the-column no matter which backend or backup tool copies it. See
docs/adr/0004-encryption-at-rest.md for the full decision and its limits.

Fernet (AES-128-CBC + HMAC-SHA256, random IV per value) is authenticated: a wrong
key or a tampered value raises `DecryptionError` instead of returning garbage,
which matters for an audit log whose whole purpose is to be trustworthy.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import Text, text
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

DATA_KEY_ENV_VAR = "CHEMSENTRY_DATA_KEY"
ENVIRONMENT_ENV_VAR = "CHEMSENTRY_ENV"

# Marks a stored value as ciphertext and versions the scheme, so a future
# algorithm change can coexist with old rows, and so rows written before
# encryption existed (no prefix) are recognisable and can be migrated.
CIPHERTEXT_PREFIX = "enc:v1:"

# Dev-only fallback key location (gitignored). Unlike the JWT dev key, this is
# NOT a shared well-known constant: it is generated randomly per machine, so a
# leaked dev database cannot be decrypted with a key read out of the source.
_DEV_KEY_FILE = Path(__file__).resolve().parent.parent / ".chemsentry_data.key"

_legacy_warning_emitted = False


class EncryptionKeyError(RuntimeError):
    """The data-encryption key is missing or malformed."""


class DecryptionError(Exception):
    """A stored value could not be decrypted (wrong key, or value was tampered)."""


def _is_production() -> bool:
    """True when CHEMSENTRY_ENV=production, which forbids the dev key fallback."""
    return os.getenv(ENVIRONMENT_ENV_VAR, "development").strip().lower() == "production"


def _load_or_create_dev_key() -> str:
    """Return the persisted per-machine dev key, creating it on first use.

    Persisting matters: an ephemeral per-process key would make every alert
    written before a server restart permanently unreadable after it.
    """
    if _DEV_KEY_FILE.exists():
        return _DEV_KEY_FILE.read_text(encoding="utf-8").strip()
    key = Fernet.generate_key().decode("ascii")
    _DEV_KEY_FILE.write_text(key, encoding="utf-8")
    try:
        _DEV_KEY_FILE.chmod(0o600)
    except OSError:
        pass  # best effort; Windows ignores POSIX modes
    logger.warning(
        "%s is not set -- generated a random local dev key at %s (gitignored). "
        "Set %s explicitly for any shared or deployed environment.",
        DATA_KEY_ENV_VAR,
        _DEV_KEY_FILE,
        DATA_KEY_ENV_VAR,
    )
    return key


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet:
    """Build (once) the cipher from CHEMSENTRY_DATA_KEY, or the dev fallback.

    CHEMSENTRY_DATA_KEY may hold several comma-separated keys, newest first:
    MultiFernet encrypts with the first and decrypts with any, which is what
    makes key rotation possible without losing old rows.
    """
    raw = os.getenv(DATA_KEY_ENV_VAR, "").strip()
    if raw:
        keys = [k.strip() for k in raw.split(",") if k.strip()]
    elif _is_production():
        raise EncryptionKeyError(
            f"{DATA_KEY_ENV_VAR} must be set when {ENVIRONMENT_ENV_VAR}=production. "
            "Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    else:
        keys = [_load_or_create_dev_key()]
    try:
        return MultiFernet([Fernet(k.encode("ascii")) for k in keys])
    except (ValueError, TypeError) as exc:
        raise EncryptionKeyError(
            f"{DATA_KEY_ENV_VAR} (or the dev key file) is not a valid Fernet key: "
            "expected 32 url-safe base64-encoded bytes."
        ) from exc


def reset_key_cache() -> None:
    """Forget the cached cipher so the next call re-reads the environment (tests)."""
    _cipher.cache_clear()


def validate_key_configuration() -> None:
    """Fail fast at startup if the key is unusable, rather than at the first alert."""
    _cipher()


def is_encrypted(value: str) -> bool:
    """True if `value` carries this module's ciphertext marker."""
    return value.startswith(CIPHERTEXT_PREFIX)


def encrypt_str(plaintext: str) -> str:
    """Encrypt a string into a self-describing, storable ciphertext string."""
    token = _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return CIPHERTEXT_PREFIX + token


def decrypt_str(stored: str) -> str:
    """Decrypt a stored value; tolerate (and flag) pre-encryption plaintext rows.

    Rows written before this module existed have no prefix. Returning them
    unchanged keeps an existing local database working until
    `encrypt_existing_plaintext` upgrades it (which init_db does at startup).
    """
    global _legacy_warning_emitted
    if not is_encrypted(stored):
        if not _legacy_warning_emitted:
            _legacy_warning_emitted = True
            logger.warning(
                "Read an unencrypted legacy value from an encrypted column; "
                "it will be encrypted on the next init_db()."
            )
        return stored
    try:
        return (
            _cipher()
            .decrypt(stored[len(CIPHERTEXT_PREFIX) :].encode("ascii"))
            .decode("utf-8")
        )
    except InvalidToken as exc:
        raise DecryptionError(
            "Could not decrypt a stored value: wrong key, or the value was modified."
        ) from exc


class EncryptedText(TypeDecorator):
    """A TEXT column whose value is encrypted on write and decrypted on read."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return None if value is None else encrypt_str(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        return None if value is None else decrypt_str(value)


class EncryptedJSON(TypeDecorator):
    """A JSON-serialisable value stored as encrypted text (JSON is not queryable
    once encrypted, which is acceptable: no route filters inside `details`)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        return None if value is None else encrypt_str(json.dumps(value))

    def process_result_value(self, value: str | None, dialect: Any) -> Any:
        return None if value is None else json.loads(decrypt_str(value))


def encrypt_existing_plaintext(engine: Any, metadata: Any) -> int:
    """Encrypt, in place, any value in an encrypted column that predates encryption.

    Problem this solves: `create_all` never alters existing tables, and every
    teammate already has a local chemsentry.db full of plaintext alerts. Without
    this, "encryption at rest" would only protect rows created after the change.

    The columns to upgrade are discovered from the models' own column types
    (single source of truth) rather than a second hand-maintained list. Raw SQL
    is used on purpose so the TypeDecorators don't try to decrypt/re-encrypt.
    Idempotent: already-encrypted and NULL values are skipped. Only text-valued
    columns are handled (SQLite / TEXT); a legacy Postgres JSON column would
    need a one-off ALTER, which no deployment has needed so far.

    Returns the number of values encrypted.
    """
    quote = engine.dialect.identifier_preparer.quote
    migrated = 0
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            encrypted_columns = [
                c
                for c in table.columns
                if isinstance(c.type, (EncryptedText, EncryptedJSON))
            ]
            if not encrypted_columns:
                continue
            pk = next(iter(table.primary_key.columns)).name
            for column in encrypted_columns:
                rows = conn.execute(
                    text(
                        f"SELECT {quote(pk)}, {quote(column.name)} FROM {quote(table.name)}"
                    )
                ).fetchall()
                for pk_value, raw in rows:
                    if raw is None or not isinstance(raw, str) or is_encrypted(raw):
                        continue
                    conn.execute(
                        text(
                            f"UPDATE {quote(table.name)} SET {quote(column.name)} = :v "
                            f"WHERE {quote(pk)} = :pk"
                        ),
                        {"v": encrypt_str(raw), "pk": pk_value},
                    )
                    migrated += 1
    if migrated:
        logger.info("Encrypted %d legacy plaintext value(s) at rest.", migrated)
        if engine.dialect.name == "sqlite":
            _vacuum_sqlite(engine)
    return migrated


def _vacuum_sqlite(engine: Any) -> None:
    """Rewrite the SQLite file so the pre-encryption plaintext is really gone.

    Problem this solves: an UPDATE only marks the old row's pages free -- it does
    not erase them. Measured while building this: after migrating five rows, the
    old plaintext still appeared 1184 times in the raw file; after VACUUM, zero.
    Without this step "encrypted at rest" would still leak through a copied file.
    VACUUM cannot run inside a transaction, hence AUTOCOMMIT.
    """
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").exec_driver_sql("VACUUM")
