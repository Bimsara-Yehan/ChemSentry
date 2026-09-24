# ADR 0004: Field-Level Encryption at Rest for Alert and Audit Data

**Date:** 2026-09-24  
**Status:** Accepted  
**Owner:** M4 (API / persistence)  

## Context
Alerts and the audit log are persisted (`api/db_models.py`) in SQLite locally and
PostgreSQL when deployed. Both are ordinary files/dumps: a laptop backup, a leaked
`chemsentry.db`, or a copied dump exposes every alert narrative, every sign-off note
and every "which user did what" entry in the clear. A repo audit flagged "no encryption
at rest" as an open gap. Passwords were already covered (bcrypt hashes, never stored
reversibly), so the gap was specifically the *content* of the alert/audit tables.

Constraints that shaped the decision:
* The same code must run on SQLite (dev/CI, Windows and Linux) and PostgreSQL.
* Route code and the UI must not change, and existing local databases must keep working.
* No route may lose the ability to filter or order by the columns it uses today.
* Zero budget, no native builds on the team's Windows machines.

## Decision
**Encrypt the sensitive columns individually at the ORM boundary with Fernet
(`cryptography`), implemented as SQLAlchemy `TypeDecorator`s in `api/crypto.py`.**

| Table | Encrypted | Left plaintext (and why) |
|---|---|---|
| `alerts` | `reasoning`, `notes`, `created_by`, `signed_by` | `alert_id` (lookup key), `status`, `zone_id`, `chemical_name`, numeric values, timestamps |
| `audit_log` | `user_id`, `details` | `action`, `resource` (joins the trail to its alert), `timestamp` |

The line is deliberately "human-authored text and identities are encrypted; the columns
the application filters, sorts or joins on are not". Ciphertext with a random IV can
never match an equality filter, so encrypting a queried column would silently break the
query rather than fail loudly.

Design details:
* **Authenticated encryption.** Fernet is AES-128-CBC + HMAC-SHA256. A wrong key or a
  modified value raises `DecryptionError` -- it never returns garbage. This matters for
  an audit log whose purpose is to be trusted.
* **Self-describing values.** Stored as `enc:v1:<token>`. The prefix versions the scheme
  and lets the code tell ciphertext from pre-encryption plaintext.
* **Key management.** `CHEMSENTRY_DATA_KEY` holds the key. Several comma-separated keys
  (newest first) enable rotation: the first encrypts, any decrypts. With
  `CHEMSENTRY_ENV=production` a missing key is a hard startup failure (`init_db()`
  validates it). In development, if unset, a random per-machine key is generated once
  and persisted to `.chemsentry_data.key` (gitignored). It is **not** a shared constant
  in the source, so a leaked dev database cannot be decrypted with a key read from the
  repo, and it persists so alerts survive a server restart.
* **Migration of existing databases.** `create_all` never alters existing tables and every
  teammate already has a local database full of plaintext alerts, so `init_db()` runs an
  idempotent `encrypt_existing_plaintext()` that upgrades those rows in place. The columns
  to upgrade are discovered from the model column types, not a second hand-kept list.
* **SQLite free pages.** An `UPDATE` does not erase the old row: measured while building
  this, after migrating five rows the old plaintext still appeared **1184 times** in the
  raw file, and **0** after a `VACUUM`. The migration therefore `VACUUM`s SQLite after
  rewriting rows, and a test asserts on the raw bytes of the file, not just on query
  results.

## Alternatives Rejected
* **SQLCipher (whole-database encryption).**
  *Rejected:* needs a native, platform-specific build (painful on Windows and in CI),
  covers only the SQLite path, and is unavailable on PostgreSQL where the code must also
  run. It would also make the database unreadable to ordinary tooling for the whole team.
* **Rely on OS/disk encryption (BitLocker, LUKS, encrypted cloud volumes) only.**
  *Rejected as the sole control:* it protects a powered-off disk, not a copied file, a
  backup, or a dump. It remains the right complement for the columns left plaintext (see
  below) and is the recommended production configuration.
* **Deterministic encryption (so encrypted columns stay filterable).**
  *Rejected:* equal plaintexts would produce equal ciphertexts, leaking which sign-off
  notes or users repeat. Nothing needs to filter on these columns today.
* **Encrypt every column.**
  *Rejected:* breaks `alert_id` lookup and ordering for no security gain on non-sensitive
  values, and would make the database undiagnosable.

## Consequences
* **Positive:** a copied `chemsentry.db` or dump reveals no alert narratives, sign-off
  notes, or user identities; tampering with an encrypted value is detected; route code,
  API responses and the UI are unchanged; existing databases are upgraded automatically.
* **Positive:** portable and testable with plain pytest (14 tests, including one that
  inspects the real tables and raw file bytes).
* **Negative / residual exposure (stated plainly):** `zone_id`, `chemical_name`, numeric
  readings, statuses, `action`, `resource` and timestamps remain readable in the database
  file. Someone with the file can see *that* an excursion of a given chemical in a given
  zone occurred, not the narrative or who handled it. Production should add PostgreSQL
  with volume/TDE encryption to cover these.
* **Negative:** the key is now a critical secret. Losing it makes the encrypted columns
  unrecoverable; leaking it defeats the protection. Store it in a secrets manager, not in
  the repo or `.env` committed anywhere. Rotation is supported for *decryption*; a bulk
  re-encryption job to retire an old key is not built yet.
* **Negative:** the migration handles text-valued columns. A pre-existing PostgreSQL
  deployment with the old `JSON` column type would need a one-off `ALTER`; none exists.
* **Out of scope:** backups or journal files taken *before* migration still contain
  plaintext; encryption in transit (TLS) is a separate control; the JWT signing-key
  fallback is tracked separately.
