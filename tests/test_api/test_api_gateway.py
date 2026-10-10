"""Tests for ChemSentry API Gateway (M4).

Tests health check, authentication (JWT login), protected routes, RBAC, safety evaluation, and error handling.
"""

import re
from datetime import date
from pathlib import Path

import pytest
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
    target_alert_id = alerts[0][
        "alert_id"
    ]  # newest-first; this is the one just created

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


def test_list_alerts_returns_newest_first():
    """A supervisor working the queue needs the most recent excursion visible
    without scrolling past the whole history -- GET /alerts must order by
    id descending, not insertion order."""
    headers = _analyst_headers()
    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 45.0,
        "unit": "C",
    }
    client.post("/safety/evaluate", json=eval_payload, headers=headers)
    first_alert_id = client.get("/alerts", headers=headers).json()["alerts"][0][
        "alert_id"
    ]

    client.post("/safety/evaluate", json=eval_payload, headers=headers)
    alerts_after = client.get("/alerts", headers=headers).json()["alerts"]

    assert alerts_after[0]["alert_id"] != first_alert_id
    ids = [int(a["alert_id"].split("_")[1]) for a in alerts_after]
    assert ids == sorted(ids, reverse=True)


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
    assert data["evidence"]["suggested_chemical"] is None


def test_query_suggests_but_never_substitutes_a_near_miss_name():
    """A typo must not come back showing another document's limits under the
    typed name -- the UI titles results with query.chemical_name."""
    response = client.post(
        "/query", json={"chemical_name": "Tolune"}, headers=_analyst_headers()
    )
    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence["thresholds"] == []
    assert evidence["suggested_chemical"] == "Toluene"


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
    alert_id = alerts[0]["alert_id"]  # newest-first; this is the one just created

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


# ============================================================================
# User Management Tests (M4)
# ============================================================================


def _admin_headers():
    login_res = client.post(
        "/auth/login", json={"username": "admin_user", "password": "admin123"}
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_user_and_login():
    """Verify admin can create a real DB user and that user can log in."""
    headers = _admin_headers()
    payload = {
        "username": "new_lab_tech",
        "password": "techpassword123",
        "role": "analyst",
    }
    create_res = client.post("/users", json=payload, headers=headers)
    assert create_res.status_code == 201
    user_data = create_res.json()
    assert user_data["username"] == "new_lab_tech"
    assert user_data["role"] == "analyst"
    assert user_data["is_active"] is True

    # Try logging in as the newly created user
    login_res = client.post(
        "/auth/login",
        json={"username": "new_lab_tech", "password": "techpassword123"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # List users and verify new_lab_tech is present
    list_res = client.get("/users", headers=headers)
    assert list_res.status_code == 200
    usernames = [u["username"] for u in list_res.json()]
    assert "new_lab_tech" in usernames


def test_create_user_rbac_restriction():
    """Verify non-admin cannot create users."""
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    payload = {
        "username": "unauthorized_user",
        "password": "password123",
        "role": "viewer",
    }
    res = client.post("/users", json=payload, headers=headers)
    assert res.status_code == 403


# ============================================================================
# Zone Management Tests (M4)
# ============================================================================


def test_zone_management_crud():
    """Verify zone creation, adding chemicals, and removing chemicals."""
    headers = _admin_headers()

    # Create new zone
    zone_payload = {"zone_id": "Zone_Test", "chemicals": ["Ethanol"]}
    create_res = client.post("/zones", json=zone_payload, headers=headers)
    assert create_res.status_code == 201
    assert create_res.json()["zone_id"] == "Zone_Test"
    assert "Ethanol" in create_res.json()["chemicals"]

    # Add chemical to zone
    add_chem_res = client.post(
        "/zones/Zone_Test/chemicals",
        json={"chemical_name": "Acetone"},
        headers=headers,
    )
    assert add_chem_res.status_code == 201
    assert "Acetone" in add_chem_res.json()["chemicals"]

    # Remove chemical from zone
    del_chem_res = client.delete("/zones/Zone_Test/chemicals/Ethanol", headers=headers)
    assert del_chem_res.status_code == 200
    assert "Ethanol" not in del_chem_res.json()["chemicals"]
    assert "Acetone" in del_chem_res.json()["chemicals"]


# ============================================================================
# Audit Log Tests (M4)
# ============================================================================


def test_get_audit_log_endpoint():
    """Verify audit log endpoint returns entries and pagination info for ADMIN."""
    headers = _admin_headers()
    res = client.get("/audit-log?limit=10&offset=0", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "entries" in data
    assert "total" in data
    assert isinstance(data["entries"], list)


# ============================================================================
# SDS Document Upload Tests (M4)
# ============================================================================

_TEST_SDS_PDF_BYTES = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 120 >>
stream
BT
/F1 12 Tf
50 700 Td
(Product name : Testium) Tj
0 -20 Td
(Company : Test Supplier) Tj
0 -20 Td
(SECTION 7: Handling and storage) Tj
0 -20 Td
(Store below 12 C.) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000223 00000 n 
0000000290 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
460
%%EOF"""


@pytest.fixture
def isolated_corpus(tmp_path, monkeypatch):
    """Upload tests write real files. Point them at a temp directory -- the
    real corpus/raw/ is loaded into the live corpus at API startup, and
    earlier runs left dozens of "Testium" fixtures there -- and restore the
    in-memory corpus afterwards so uploads don't leak into other tests."""
    monkeypatch.setattr(main, "CORPUS_RAW_DIR", tmp_path)
    monkeypatch.setattr(main, "_PROCESSED_DOCUMENTS", list(main._PROCESSED_DOCUMENTS))
    monkeypatch.setattr(main, "retriever", main.retriever)
    return tmp_path


def test_upload_sds_document_and_query_retrieval(isolated_corpus):
    """Verify admin can upload a new SDS PDF, extract thresholds, and query immediately."""
    headers = _admin_headers()
    files = {"file": ("test_sds_upload.pdf", _TEST_SDS_PDF_BYTES, "application/pdf")}

    upload_res = client.post("/corpus/documents", files=files, headers=headers)
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    assert upload_data["chemical_name"] == "Testium"
    assert upload_data["supplier"] == "Test Supplier"

    # Query the newly uploaded chemical in the SAME test
    query_res = client.post(
        "/query", json={"chemical_name": "Testium"}, headers=headers
    )
    assert query_res.status_code == 200
    query_data = query_res.json()
    thresholds = query_data["evidence"]["thresholds"]
    assert len(thresholds) > 0
    assert thresholds[0]["parameter"] == "max_storage_temperature"
    assert thresholds[0]["value"] == 12.0
    assert thresholds[0]["unit"] == "C"


def test_upload_sds_document_rbac_restriction():
    """Verify non-admin cannot upload SDS documents."""
    login_res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    files = {"file": ("test_sds_upload.pdf", _TEST_SDS_PDF_BYTES, "application/pdf")}
    res = client.post("/corpus/documents", files=files, headers=headers)
    assert res.status_code == 403


def test_upload_filename_is_never_used_as_a_path(isolated_corpus):
    """A path-traversal-shaped filename must not escape corpus/raw/, and the
    on-disk name must never be derived from attacker-controlled input --
    the stored path is a fresh UUID regardless of what the client named the
    file. Proves the real fix, not just that the upload still returns 200
    for a well-behaved filename."""
    import api.main as main

    headers = _admin_headers()
    malicious_names = [
        "../../../../etc/evil.pdf",
        "..\\..\\windows\\evil.pdf",
        "/etc/passwd.pdf",
    ]
    for name in malicious_names:
        files = {"file": (name, _TEST_SDS_PDF_BYTES, "application/pdf")}
        res = client.post("/corpus/documents", files=files, headers=headers)
        assert res.status_code == 201, name
        data = res.json()

        assert data["original_filename"] == name  # shown back, never trusted as a path
        source_path = Path(data["source_path"]).resolve()
        assert source_path.parent == main.CORPUS_RAW_DIR.resolve()
        assert source_path.is_relative_to(main.CORPUS_RAW_DIR.resolve())
        # The saved name must be the safe id regex the crawler already
        # enforces (corpus/crawler/storage.py's _SAFE_ID_RE), never a
        # literal fragment of the malicious name.
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.pdf", source_path.name), name
        assert source_path.exists()


def test_upload_same_filename_twice_does_not_collide_on_disk(isolated_corpus):
    """Two uploads sharing a client-supplied filename must not silently
    overwrite each other -- the old bug this fix replaces (raw filename
    as the path) would have made the second upload clobber the first."""
    headers = _admin_headers()
    files = {"file": ("same_name.pdf", _TEST_SDS_PDF_BYTES, "application/pdf")}

    first = client.post("/corpus/documents", files=files, headers=headers)
    second = client.post("/corpus/documents", files=files, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["source_path"] != second.json()["source_path"]
    assert Path(first.json()["source_path"]).exists()
    assert Path(second.json()["source_path"]).exists()


def test_upload_rejects_non_pdf_content_even_with_pdf_extension(isolated_corpus):
    """A `.pdf`-named file proves nothing about its actual content -- the
    magic-byte check must reject it before it ever reaches pdfplumber."""
    headers = _admin_headers()
    files = {"file": ("fake.pdf", b"not actually a pdf", "application/pdf")}
    res = client.post("/corpus/documents", files=files, headers=headers)
    assert res.status_code == 400


def test_upload_name_override_survives_restart(isolated_corpus):
    """An admin's chemical-name/supplier override must still apply after the
    corpus is rebuilt from disk -- before the fix it lived only in memory,
    so a restart silently re-parsed Section 1 and lost it (a real Carl Roth
    SDS whose name the parser couldn't read became "unknown" again)."""
    headers = _admin_headers()
    files = {"file": ("roth.pdf", _TEST_SDS_PDF_BYTES, "application/pdf")}
    data = {"chemical_name": "Renamed Chemical", "supplier": "Override Supplier Ltd"}
    res = client.post("/corpus/documents", files=files, data=data, headers=headers)
    assert res.status_code == 201
    assert res.json()["chemical_name"] == "Renamed Chemical"
    assert Path(res.json()["source_path"]).with_suffix(".meta.json").is_file()

    rebuilt = main._load_retriever()  # what startup does

    thresholds = rebuilt.get_thresholds("Renamed Chemical")
    assert [t.value for t in thresholds] == [12.0]
    assert "testium" not in rebuilt.vocabulary


def test_upload_rejects_overlong_override(isolated_corpus):
    headers = _admin_headers()
    files = {"file": ("x.pdf", _TEST_SDS_PDF_BYTES, "application/pdf")}
    res = client.post(
        "/corpus/documents",
        files=files,
        data={"chemical_name": "x" * 201},
        headers=headers,
    )
    assert res.status_code == 400
    assert list(isolated_corpus.iterdir()) == []


# ============================================================================
# Remediation (#82): no invented readings, role-filtered alerts, demo accounts
# ============================================================================


def test_zone_without_a_reading_is_unknown_but_shows_its_retrieved_limits(
    monkeypatch,
):
    """No sensor has reported, so nothing is evaluated -- but the zone's SDS
    limits are still retrieved and cited rather than shown as missing."""
    monkeypatch.setattr(main, "_LATEST_ZONE_EVALUATIONS", {})
    zone = client.get("/zones/Zone_C", headers=_analyst_headers()).json()

    assert zone["last_reading"] is None
    assert zone["safety_state"] == "UNKNOWN"
    h2o2_max = next(
        c
        for c in zone["checks"]
        if c["chemical_name"] == "Hydrogen peroxide solution"
        and c["metric_name"] == "max_storage_temperature"
    )
    assert h2o2_max["state"] == "UNKNOWN"
    assert h2o2_max["current_value"] is None  # never a placeholder 0.0
    assert h2o2_max["threshold_value"] == 8.0
    assert "TEST_H2O2_001" in h2o2_max["citation"]


def test_creating_a_zone_records_no_reading():
    """A new zone used to get an invented 20 C "zone-create-default" reading."""
    headers = _admin_headers()
    created = client.post(
        "/zones",
        json={"zone_id": "Zone_NoReading", "chemicals": ["Hydrogen peroxide solution"]},
        headers=headers,
    )
    assert created.status_code == 201

    zone = client.get("/zones/Zone_NoReading", headers=headers).json()
    assert zone["last_reading"] is None
    assert zone["safety_state"] == "UNKNOWN"


def test_alerts_are_filtered_by_role():
    client.post(
        "/safety/evaluate",
        json={
            "chemical_name": "Toluene",
            "zone_id": "Zone_B",
            "metric_name": "max_storage_temperature",
            "current_value": 40.0,
            "unit": "C",
        },
        headers=_analyst_headers(),
    )

    def newest_alert(username: str, password: str) -> dict:
        token = client.post(
            "/auth/login", json={"username": username, "password": password}
        ).json()["access_token"]
        alerts = client.get(
            "/alerts", headers={"Authorization": f"Bearer {token}"}
        ).json()["alerts"]
        return alerts[0]

    viewer = newest_alert("viewer_user", "viewer123")
    analyst = newest_alert("analyst_user", "analyst123")
    admin = newest_alert("admin_user", "admin123")

    assert viewer["chemical_name"] == "Toluene"
    assert "reasoning" not in viewer and "current_value" not in viewer
    assert analyst["reasoning"] and analyst["current_value"] == 40.0
    assert "created_by" not in analyst and "notes" not in analyst
    assert admin["created_by"] == "analyst_user"


def test_demo_accounts_cannot_log_in_in_production(monkeypatch):
    from api.security import authenticate_user

    monkeypatch.setenv("CHEMSENTRY_ENV", "production")
    assert authenticate_user("admin_user", "admin123") is None


def test_database_users_still_log_in_in_production(monkeypatch):
    """Only the demo fallback is disabled in production, not login itself."""
    from api.db_models import UserRecord
    from api.models import UserRole
    from api.security import authenticate_user, hash_password

    db = SessionLocal()
    try:
        # Written before switching to production, as an admin would have
        # created it while the system was running.
        db.add(
            UserRecord(
                user_id="user_prod_test",
                username="prod_operator",
                password_hash=hash_password("s3cure-pass!"),
                role="analyst",
                is_active=True,
            )
        )
        db.commit()

        monkeypatch.setenv("CHEMSENTRY_ENV", "production")
        assert authenticate_user("prod_operator", "s3cure-pass!", db=db) == (
            "user_prod_test",
            UserRole.ANALYST,
        )
    finally:
        db.query(UserRecord).filter(UserRecord.username == "prod_operator").delete()
        db.commit()
        db.close()
