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

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped

from api.database import Base


class AlertRecord(Base):
    """One safety alert raised by a WARNING evaluation, through sign-off.

    Deliberately denormalised (one row per alert, not split across an
    "evaluation" + "sign-off" table) -- this mirrors exactly what the old
    in-memory dict already stored, just made durable, rather than expanding
    scope into a schema redesign.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = Column(String, unique=True, nullable=False, index=True)
    zone_id: Mapped[str] = Column(String, nullable=False)
    chemical_name: Mapped[str] = Column(String, nullable=False)
    current_value: Mapped[float] = Column(Float, nullable=False)
    unit: Mapped[str] = Column(String, nullable=False)
    threshold_value: Mapped[float] = Column(Float, nullable=True)
    reasoning: Mapped[str] = Column(Text, nullable=False)
    status: Mapped[str] = Column(String, nullable=False, default="pending_review")
    created_by: Mapped[str] = Column(String, nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, nullable=False)
    signed_by: Mapped[str] = Column(String, nullable=True)
    notes: Mapped[str] = Column(Text, nullable=True)
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
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = Column(String, nullable=False)  # "alert_created" | "sign_off"
    user_id: Mapped[str] = Column(String, nullable=False)
    resource: Mapped[str] = Column(String, nullable=False)  # the alert_id this is about
    details: Mapped[dict] = Column(JSON, nullable=False)
    timestamp: Mapped[datetime] = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


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
