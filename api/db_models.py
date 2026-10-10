"""SQLAlchemy ORM tables for persistent alert and audit-log storage (M4).

Before this module existed, `api/main.py` kept alerts in `ALERTS_REGISTRY`,
a plain in-memory Python list -- every alert and sign-off decision was lost
on process restart. `api/models.py`'s `AuditLog` Pydantic model was defined
but never instantiated anywhere in the codebase (confirmed by grep: its only
occurrence was its own class definition). The plan (§17) requires "an
append-only audit log of every alert and sign-off"; neither requirement was
actually met by code that merely defines a schema nobody writes to.

These tables are created by `api.database.init_db()` at startup -- that only
works if this module has been imported by then (so these classes are
registered on `Base.metadata`), which `api/main.py` does at import time.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped

from api.crypto import EncryptedJSON, EncryptedText
from api.database import Base


class UserRecord(Base):
    """Real user account table for authentication and RBAC (M4).

    Encryption at rest (api/crypto.py, ADR 0004): password_hash is stored as
    EncryptedText. Plaintext columns (username, role, created_at, is_active)
    stay unencrypted so they can be queried and filtered efficiently.
    """

    __tablename__ = "users"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = Column(String, unique=True, nullable=False, index=True)
    username: Mapped[str] = Column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = Column(EncryptedText, nullable=False)
    role: Mapped[str] = Column(String, nullable=False, default="viewer")
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AlertRecord(Base):
    """One safety alert raised by a WARNING evaluation, through sign-off.

    Deliberately denormalised (one row per alert, not split across an
    "evaluation" + "sign-off" table) -- this mirrors exactly what the old
    in-memory dict already stored, just made durable, rather than expanding
    scope into a schema redesign.

    Encryption at rest (api/crypto.py, ADR 0004): the human-authored and
    identity columns -- reasoning, notes, created_by, signed_by -- are stored
    as ciphertext. The columns the app filters, sorts or joins on (alert_id,
    status, zone_id, chemical_name, numeric values, timestamps) stay plaintext
    because ciphertext with a random IV can never match an equality filter;
    production covers those with database/volume encryption instead.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = Column(String, unique=True, nullable=False, index=True)
    zone_id: Mapped[str] = Column(String, nullable=False)
    chemical_name: Mapped[str] = Column(String, nullable=False)
    current_value: Mapped[float] = Column(Float, nullable=False)
    unit: Mapped[str] = Column(String, nullable=False)
    threshold_value: Mapped[float] = Column(Float, nullable=True)
    reasoning: Mapped[str] = Column(EncryptedText, nullable=False)
    status: Mapped[str] = Column(String, nullable=False, default="pending_review")
    created_by: Mapped[str] = Column(EncryptedText, nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, nullable=False)
    signed_by: Mapped[str] = Column(EncryptedText, nullable=True)
    notes: Mapped[str] = Column(EncryptedText, nullable=True)
    signed_at: Mapped[datetime] = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        """Serialise to the same shape the old in-memory dict records used,
        so existing API consumers (the UI, tests) see an unchanged response
        shape even though storage moved from a list to a real table."""
        return {
            "alert_id": self.alert_id,
            "zone_id": self.zone_id,
            "chemical_name": self.chemical_name,
            "current_value": self.current_value,
            "unit": self.unit,
            "threshold_value": self.threshold_value,
            "reasoning": self.reasoning,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "signed_by": self.signed_by,
            "notes": self.notes,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
        }


class AuditLogRecord(Base):
    """Append-only audit trail (plan §17): one row per alert raised or
    sign-off decision made.

    "Append-only" is enforced by convention, not a DB constraint: no route
    in api/main.py ever issues an UPDATE or DELETE against this table, only
    INSERT. A real deployment would additionally revoke UPDATE/DELETE grants
    at the database-user level; out of scope for local/SQLite dev.

    Encryption at rest (api/crypto.py, ADR 0004): user_id (who acted) and
    details (the values/notes involved) are ciphertext; action, resource and
    timestamp stay plaintext so the trail can still be ordered and joined to
    its alert by `resource`.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = Column(String, nullable=False)  # "alert_created" | "sign_off"
    user_id: Mapped[str] = Column(EncryptedText, nullable=False)
    resource: Mapped[str] = Column(String, nullable=False)  # the alert_id this is about
    details: Mapped[dict] = Column(EncryptedJSON, nullable=False)
    timestamp: Mapped[datetime] = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


def alert_to_dict(alert: AlertRecord, role: str) -> dict:
    """Role-aware serializer for GET /alerts, so each role sees only what it needs.

    AlertRecord.to_dict() returns every column, including who raised and
    signed an alert and the sign-off notes (encrypted at rest because they
    are identity and free text, see the class docstring). Viewers only need
    what was flagged and its status; analysts also need the values and
    reasoning to investigate; sign-off identity and notes stay with admins.
    """
    role_str = role.value if hasattr(role, "value") else str(role)
    data = {
        "alert_id": alert.alert_id,
        "zone_id": alert.zone_id,
        "chemical_name": alert.chemical_name,
        "status": alert.status,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }
    # Operational metrics exposed to analyst and admin
    if role_str in ("analyst", "admin"):
        data["reasoning"] = alert.reasoning
        data["threshold_value"] = alert.threshold_value
        data["current_value"] = alert.current_value
        data["unit"] = alert.unit
    # PII and investigator notes restricted strictly to administrators
    if role_str == "admin":
        data["created_by"] = alert.created_by
        data["signed_by"] = alert.signed_by
        data["notes"] = alert.notes
        data["signed_at"] = alert.signed_at.isoformat() if alert.signed_at else None
    return data


def next_alert_id(db) -> str:
    """Generate the next sequential alert_id (ALT_0001, ALT_0002, ...).

    Simple count-based scheme, matching the old in-memory registry's
    `len(ALERTS_REGISTRY) + 1` approach -- adequate for a single-process
    demo app; not safe under concurrent writers, which this app has none of.
    """
    count = db.query(AlertRecord).count()
    return f"ALT_{count + 1:04d}"


class ZoneInventoryRecord(Base):
    """Which chemicals are stored in which zone (Agent C, M4).

    Plan §16: "Inventory is database-backed and simulated ... Container
    tracking is not our research contribution." This is deliberately that --
    a flat zone-to-chemical mapping, not real-time RFID/container tracking.
    Agent C (agents/agent_c_environment/) reads this to know which real
    chemicals' thresholds to check whenever a zone's sensor reading changes;
    it never hardcodes a chemical's safety limit itself, only which
    chemicals are physically present.
    """

    __tablename__ = "zone_inventory"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[str] = Column(String, nullable=False, index=True)
    chemical_name: Mapped[str] = Column(String, nullable=False)


def next_user_id(db) -> str:
    """Generate next user_id (USR_0001, USR_0002, ...)."""
    count = db.query(UserRecord).count()
    return f"USR_{count + 1:04d}"
