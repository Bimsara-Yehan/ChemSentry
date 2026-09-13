"""Unit tests for the zone-inventory DB loader/seeder (Agent C, M4).

Uses an isolated in-memory SQLite engine bound to the shared `Base`, not the
project's real `chemsentry.db` file -- these tests must not depend on, or
pollute, whatever state that file happens to hold on a given machine or CI
run.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.agent_c_environment.zone_inventory import (
    DEFAULT_ZONE_INVENTORY,
    load_zone_inventory,
    seed_default_zone_inventory,
)
from api.database import Base
from api.db_models import ZoneInventoryRecord  # noqa: F401 -- registers the table


def _session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_seed_populates_empty_table() -> None:
    db = _session()
    inserted = seed_default_zone_inventory(db)

    total_chemicals = sum(len(v) for v in DEFAULT_ZONE_INVENTORY.values())
    assert inserted == total_chemicals


def test_seed_is_idempotent() -> None:
    db = _session()
    seed_default_zone_inventory(db)
    second_call_inserted = seed_default_zone_inventory(db)

    assert second_call_inserted == 0


def test_load_zone_inventory_round_trips_default_data() -> None:
    db = _session()
    seed_default_zone_inventory(db)

    loaded = load_zone_inventory(db)
    assert loaded == DEFAULT_ZONE_INVENTORY


def test_load_zone_inventory_on_empty_table_returns_empty_dict() -> None:
    db = _session()
    assert load_zone_inventory(db) == {}
