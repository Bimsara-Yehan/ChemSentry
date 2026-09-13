"""Database-backed zone-to-chemical inventory loader/seeder (Agent C, M4).

Plan §16: "Inventory is database-backed and simulated ... Container tracking
is not our research contribution." This module is the thin DB-facing layer
around that flat mapping -- `api/db_models.py`'s `ZoneInventoryRecord` is the
table, this module is how it gets seeded and read back into the plain
`dict[str, list[str]]` shape `EnvironmentalMonitor` (monitor.py) consumes.

Seed data note (verified against real corpus/raw/ documents, not invented):
Every chemical named below has its own real SDS in this project's corpus
(cross-checked against evaluation/benchmarks/layer3_extraction_quality.csv).
But only **Hydrogen peroxide solution** (216763.pdf) has a real numeric
storage-temperature range extracted from its SDS (2.0-8.0 C, Section 7,
label:value field) -- every other chemical below has no storage-temperature
field in its real SDS text at all (confirmed while building Layer 3: Acetone,
Ethanol, and Potassium permanganate's SDS say only "see product label" with
no number; Sodium hydroxide, Sulfuric acid, Hydrochloric acid, Zinc oxide and
2-Propanol's SDS have no such field whatsoever). Zones A and B will therefore
genuinely evaluate to UNKNOWN for the temperature metrics forever, given this
corpus -- that is the deterministic safety layer working correctly ("never
force a SAFE/WARNING verdict when evidence is missing"), not a bug in this
module. Zone C's hydrogen peroxide is deliberately the only chemical in this
seed that can ever produce a real SAFE or WARNING verdict from this corpus,
so tests and demos have at least one real, non-UNKNOWN path to exercise.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from api.db_models import ZoneInventoryRecord

# zone_id -> chemicals physically stored there. Grouped the way the
# apriori_discovery.py incompatibility pairs group them (solvents / acids &
# bases / oxidizers) so this same seed doubles as plausible co-storage
# transaction data for Agent B, rather than an unrelated arbitrary split.
DEFAULT_ZONE_INVENTORY: dict[str, list[str]] = {
    "Zone_A": ["Ethanol", "2-Propanol", "Acetone"],
    "Zone_B": ["Sodium hydroxide", "Hydrochloric acid", "Sulfuric acid"],
    "Zone_C": ["Hydrogen peroxide solution", "Potassium permanganate"],
}


def seed_default_zone_inventory(db: Session) -> int:
    """Populate `zone_inventory` with `DEFAULT_ZONE_INVENTORY`, if empty.

    Idempotent -- a no-op if the table already has any rows, so calling this
    at every app startup (mirroring `init_db()`) never duplicates rows.

    Returns:
        Number of rows inserted (0 if the table was already populated).
    """
    if db.query(ZoneInventoryRecord).first() is not None:
        return 0

    rows = [
        ZoneInventoryRecord(zone_id=zone_id, chemical_name=chemical_name)
        for zone_id, chemicals in DEFAULT_ZONE_INVENTORY.items()
        for chemical_name in chemicals
    ]
    db.add_all(rows)
    db.commit()
    return len(rows)


def load_zone_inventory(db: Session) -> dict[str, list[str]]:
    """Read the `zone_inventory` table into the plain dict `EnvironmentalMonitor` expects.

    Kept separate from `EnvironmentalMonitor` itself so the monitor's core
    logic stays database-free and unit-testable without a real session.
    """
    inventory: dict[str, list[str]] = {}
    for row in db.query(ZoneInventoryRecord).order_by(ZoneInventoryRecord.id).all():
        inventory.setdefault(row.zone_id, []).append(row.chemical_name)
    return inventory
