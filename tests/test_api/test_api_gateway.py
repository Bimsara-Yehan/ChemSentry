"""Tests for ChemSentry API Gateway (M4).

Tests health check, authentication (JWT login), protected routes, RBAC, safety evaluation, and error handling.
"""

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


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
    login_payload = {
        "username": "viewer_user",
        "password": "viewer123"
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_invalid_credentials():
    """Verify login with wrong password returns 401 Unauthorized."""
    login_payload = {
        "username": "viewer_user",
        "password": "wrongpassword"
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 401
    data = response.json()
    assert "error" in data or "detail" in data


def test_protected_me_endpoint_with_valid_token():
    """Verify /me endpoint works with a valid Bearer token."""
    login_res = client.post("/auth/login", json={"username": "analyst_user", "password": "analyst123"})
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
    login_res = client.post("/auth/login", json={"username": "analyst_user", "password": "analyst123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    query_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B"
    }
    response = client.post("/query", json=query_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["query"]["chemical_name"] == "Toluene"


def test_rbac_query_rejected_for_viewer():
    """Verify VIEWER role is forbidden (403) from calling /query."""
    login_res = client.post("/auth/login", json={"username": "viewer_user", "password": "viewer123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    query_payload = {
        "chemical_name": "Toluene"
    }
    response = client.post("/query", json=query_payload, headers=headers)
    assert response.status_code == 403


def test_safety_evaluate_warning():
    """Verify deterministic safety evaluation returns WARNING for temperature excursion."""
    login_res = client.post("/auth/login", json={"username": "analyst_user", "password": "analyst123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 31.0,  # Exceeds retrieved threshold of 25.0 C
        "unit": "C"
    }
    response = client.post("/safety/evaluate", json=eval_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "WARNING"
    assert data["threshold_value"] == 25.0
    assert "ABC Chemicals SDS" in data["provenance"]["citation"]


def test_safety_evaluate_safe():
    """Verify deterministic safety evaluation returns SAFE when within threshold."""
    login_res = client.post("/auth/login", json={"username": "analyst_user", "password": "analyst123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 22.0,  # Below max of 25.0 C
        "unit": "C"
    }
    response = client.post("/safety/evaluate", json=eval_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "SAFE"


def test_list_alerts_and_sign_off():
    """Verify alert appears in /alerts after WARNING and can be signed off by ADMIN."""
    # 1. Trigger WARNING evaluation to generate alert
    login_analyst = client.post("/auth/login", json={"username": "analyst_user", "password": "analyst123"})
    token_analyst = login_analyst.json()["access_token"]
    headers_analyst = {"Authorization": f"Bearer {token_analyst}"}

    eval_payload = {
        "chemical_name": "Toluene",
        "zone_id": "Zone_B",
        "metric_name": "max_storage_temperature",
        "current_value": 35.0,
        "unit": "C"
    }
    client.post("/safety/evaluate", json=eval_payload, headers=headers_analyst)

    # 2. Get alerts list
    response = client.get("/alerts", headers=headers_analyst)
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) > 0
    target_alert_id = alerts[-1]["alert_id"]

    # 3. Admin sign-off
    login_admin = client.post("/auth/login", json={"username": "admin_user", "password": "admin123"})
    token_admin = login_admin.json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    params = {"alert_id": target_alert_id, "approved": True, "notes": "Verified by Safety Officer."}
    signoff_res = client.post("/admin/sign-off", params=params, headers=headers_admin)
    assert signoff_res.status_code == 200
    data = signoff_res.json()
    assert data["status"] == "sign_off_recorded"
    assert data["alert"]["status"] == "approved"
