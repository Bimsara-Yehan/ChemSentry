"""Tests for ChemSentry API Gateway (M4).

Tests health check, authentication (JWT login), protected routes, RBAC, safety evaluation, and error handling.
"""

from datetime import date

from fastapi.testclient import TestClient

import api.main as main
from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from api.database import SessionLocal
from api.db_models import AuditLogRecord
from extraction.models import SDSMetadata
from extraction.pipeline import extract_document

# api.main.retriever normally loads from corpus/raw/, which is gitignored and
# empty on a fresh clone/CI checkout -- these tests can't depend on whatever
# PDFs happen to be sitting on a given machine. Override it with a small
# fixture corpus built through the real extraction pipeline (not a
# hand-built ProvenancedThreshold) so this still exercises the genuine
# extraction -> provenance-bridge -> retrieval path end to end.
_toluene_doc = extract_document(
    "SECTION 7: Handling and storage\nStore below 25 C.\n",
    SDSMetadata(
        document_id="TEST_TOL_001",
        chemical_name="Toluene",
        supplier="ABC Chemicals",
        retrieval_date=date.today(),
    ),
)
# Hydrogen peroxide solution is one of the real DEFAULT_ZONE_INVENTORY
# chemicals (agents/agent_c_environment/zone_inventory.py, seeded into
# Zone_C) -- included here so the /zones/{zone_id}/telemetry tests below
# can drive a genuine WARNING through Agent C's real retrieval + safety-
# evaluation chain, not just prove the endpoint returns UNKNOWN.
_h2o2_doc = extract_document(
    "SECTION 7: Handling and storage\nRecommended storage temperature : 2 - 8 \xb0C\n",
    SDSMetadata(
        document_id="TEST_H2O2_001",
        chemical_name="Hydrogen peroxide solution",
        supplier="Test Supplier",
        retrieval_date=date.today(),
    ),
)
main.retriever = CorpusRetriever([_toluene_doc, _h2o2_doc])

client = TestClient(app=main.app)


def test_root_endpoint():
    """Verify root endpoint returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ChemSentry API"
    assert "version" in data


def test_health_check_endpoint():
    """Verify /health endpoint returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
    assert "database" in data
    assert "mqtt_broker" in data


def test_login_success():
    """Verify login with valid credentials returns a JWT access token."""
    login_payload = {"username": "viewer_user", "password": "viewer123"}
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_invalid_credentials():
    """Verify login with wrong password returns 401 Unauthorized."""
    login_payload = {"username": "viewer_user", "password": "wrongpassword"}
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 401
    data = response.json()
    assert "error" in data or "detail" in data


def test_protected_me_endpoint_with_valid_token():
    """Verify /me endpoint works with a valid Bearer token."""
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "analyst_user"


def test_protected_me_endpoint_without_token():
    """Verify /me endpoint rejects requests missing Authorization header."""
    response = client.get("/me")
    assert response.status_code in [401, 403]


def test_rbac_query_allowed_for_analyst():
    """Verify ANALYST role can access /query endpoint."""
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    query_payload = {"chemical_name": "Toluene", "zone_id": "Zone_B"}
    response = client.post("/query", json=query_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["query"]["chemical_name"] == "Toluene"


def test_rbac_query_rejected_for_viewer():
    """Verify VIEWER role is forbidden (403) from calling /query."""
    login_res = client.post(
        "/auth/login", json={"username": "viewer_user", "password": "viewer123"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    query_payload = {"chemical_name": "Toluene"}
    response = client.post("/query", json=query_payload, headers=headers)
    assert response.status_code == 403


def test_safety_evaluate_warning():
    """Verify deterministic safety evaluation returns WARNING for temperature excursion."""
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 31.0,  # Exceeds retrieved threshold of 25.0 C
        "unit": "C",
    }
    response = client.post("/safety/evaluate", json=eval_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "WARNING"
    assert data["threshold_value"] == 25.0
    assert "ABC Chemicals" in data["provenance"]["citation"]


def test_safety_evaluate_safe():
    """Verify deterministic safety evaluation returns SAFE when within threshold."""
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 22.0,  # Below max of 25.0 C
        "unit": "C",
    }
    response = client.post("/safety/evaluate", json=eval_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "SAFE"


def test_list_alerts_and_sign_off():
    """Verify alert appears in /alerts after WARNING and can be signed off by ADMIN."""
    # 1. Trigger WARNING evaluation to generate alert
    login_analyst = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    token_analyst = login_analyst.json()["access_token"]
    headers_analyst = {"Authorization": f"Bearer {token_analyst}"}

    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 35.0,
        "unit": "C",
    }
    client.post("/safety/evaluate", json=eval_payload, headers=headers_analyst)

    # 2. Get alerts list
    response = client.get("/alerts", headers=headers_analyst)
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) > 0
    target_alert_id = alerts[-1]["alert_id"]

    # 3. Admin sign-off
    login_admin = client.post(
        "/auth/login", json={"username": "admin_user", "password": "admin123"}
    )
    token_admin = login_admin.json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    params = {
        "alert_id": target_alert_id,
        "approved": True,
        "notes": "Verified by Safety Officer.",
    }
    signoff_res = client.post("/admin/sign-off", params=params, headers=headers_admin)
    assert signoff_res.status_code == 200
    data = signoff_res.json()
    assert data["status"] == "sign_off_recorded"
    assert data["alert"]["status"] == "approved"


def test_sign_off_unknown_alert_returns_404():
    """Signing off an alert_id that was never raised must 404, not fabricate success."""
    login_admin = client.post(
        "/auth/login", json={"username": "admin_user", "password": "admin123"}
    )
    token_admin = login_admin.json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    params = {"alert_id": "ALT_DOES_NOT_EXIST", "approved": True}
    response = client.post("/admin/sign-off", params=params, headers=headers_admin)
    assert response.status_code == 404


def test_query_never_asserts_a_safety_verdict():
    """/query only retrieves thresholds -- it must never report SAFE without running
    the deterministic evaluator against a real reading."""
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/query", json={"chemical_name": "Toluene"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["evidence"]["final_safety_state"] == "UNKNOWN"
    assert len(data["evidence"]["thresholds"]) > 0  # thresholds were still retrieved


def test_alert_and_sign_off_are_both_written_to_the_audit_log():
    """Plan §17 requires an append-only audit log of every alert and
    sign-off -- api/models.py's AuditLog Pydantic model existed but was
    never instantiated anywhere before api/db_models.py. This checks the
    real table, not just the API response shape."""
    login_analyst = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    headers_analyst = {
        "Authorization": f"Bearer {login_analyst.json()['access_token']}"
    }

    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 40.0,
        "unit": "C",
    }
    client.post("/safety/evaluate", json=eval_payload, headers=headers_analyst)

    alerts = client.get("/alerts", headers=headers_analyst).json()["alerts"]
    alert_id = alerts[-1]["alert_id"]

    login_admin = client.post(
        "/auth/login", json={"username": "admin_user", "password": "admin123"}
    )
    headers_admin = {"Authorization": f"Bearer {login_admin.json()['access_token']}"}
    client.post(
        "/admin/sign-off",
        params={"alert_id": alert_id, "approved": True, "notes": "checked"},
        headers=headers_admin,
    )

    db = SessionLocal()
    try:
        entries = (
            db.query(AuditLogRecord)
            .filter(AuditLogRecord.resource == alert_id)
            .order_by(AuditLogRecord.id)
            .all()
        )
    finally:
        db.close()

    actions = [entry.action for entry in entries]
    assert actions == ["alert_created", "sign_off"]
    assert entries[0].user_id == "analyst_user"
    assert entries[1].user_id == "admin_user"


def _analyst_headers() -> dict:
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    return {"Authorization": f"Bearer {login_res.json()['access_token']}"}


def test_list_zones_returns_real_seeded_inventory():
    """Zone_A/B/C come from the real ZoneInventoryRecord seed data
    (agents/agent_c_environment/zone_inventory.py), not a hardcoded list."""
    response = client.get("/zones", headers=_analyst_headers())
    assert response.status_code == 200
    zone_ids = {z["zone_id"] for z in response.json()["zones"]}
    assert {"Zone_A", "Zone_B", "Zone_C"} <= zone_ids


def test_get_zone_returns_404_for_unknown_zone():
    response = client.get("/zones/Zone_Nonexistent", headers=_analyst_headers())
    assert response.status_code == 404


def test_submit_zone_telemetry_produces_genuine_warning_for_real_chemical():
    """Hydrogen peroxide solution's real 2-8 C range (see the _h2o2_doc
    fixture above) means a 12 C reading in Zone_C must come back as a real,
    evidence-backed WARNING through the actual monitor -- not a mock."""
    payload = {
        "zone_id": "Zone_C",
        "temperature_celsius": 12.0,
        "humidity_percent": 40.0,
        "timestamp": "2026-01-01T00:00:00Z",
        "device_id": "test-device",
    }
    response = client.post(
        "/zones/Zone_C/telemetry", json=payload, headers=_analyst_headers()
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_state"] == "WARNING"
    assert data["is_excursion"] is True
    h2o2_check = next(
        c for c in data["checks"] if c["chemical_name"] == "Hydrogen peroxide solution"
    )
    assert h2o2_check["state"] == "WARNING"
    assert h2o2_check["threshold_value"] == 8.0
    assert "Test Supplier" in h2o2_check["citation"]


def test_submit_zone_telemetry_persists_an_alert_for_the_warning_chemical():
    payload = {
        "zone_id": "Zone_C",
        "temperature_celsius": 15.0,
        "humidity_percent": 40.0,
        "timestamp": "2026-01-01T00:00:00Z",
        "device_id": "test-device",
    }
    headers = _analyst_headers()
    client.post("/zones/Zone_C/telemetry", json=payload, headers=headers)

    alerts = client.get("/alerts", headers=headers).json()["alerts"]
    zone_c_alerts = [a for a in alerts if a["zone_id"] == "Zone_C"]
    assert any(
        a["chemical_name"] == "Hydrogen peroxide solution" for a in zone_c_alerts
    )


def test_submit_zone_telemetry_rejects_mismatched_zone_id():
    payload = {
        "zone_id": "Zone_A",
        "temperature_celsius": 20.0,
        "humidity_percent": 40.0,
        "timestamp": "2026-01-01T00:00:00Z",
        "device_id": "test-device",
    }
    response = client.post(
        "/zones/Zone_C/telemetry", json=payload, headers=_analyst_headers()
    )
    assert response.status_code == 400


def test_submit_zone_telemetry_rejected_for_viewer():
    login_res = client.post(
        "/auth/login", json={"username": "viewer_user", "password": "viewer123"}
    )
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    payload = {
        "zone_id": "Zone_C",
        "temperature_celsius": 5.0,
        "humidity_percent": 40.0,
        "timestamp": "2026-01-01T00:00:00Z",
        "device_id": "test-device",
    }
    response = client.post("/zones/Zone_C/telemetry", json=payload, headers=headers)
    assert response.status_code == 403
