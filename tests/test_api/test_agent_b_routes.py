"""API route tests for Agent B items wired in PR 1 (M3).

Tests:
  - GET /zones/{zone_id}/co-storage-check  (Item 1: co-storage / CAMEO warnings)
  - POST /alerts/{alert_id}/narrate         (Item 2: plain-language safety card)

All tests use the shared TestClient from test_api_gateway.py which already
sets up the fixture retriever and the isolated test database via conftest.py.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import api.main as main

# Reuse the TestClient bound to main.app -- conftest.py already redirected
# DATABASE_URL to the temp SQLite file before this import happens.
client = TestClient(app=main.app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _analyst_token() -> dict:
    """Return Authorization headers for analyst_user."""
    res = client.post(
        "/auth/login", json={"username": "analyst_user", "password": "analyst123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _viewer_token() -> dict:
    """Return Authorization headers for viewer_user."""
    res = client.post(
        "/auth/login", json={"username": "viewer_user", "password": "viewer123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Item 1 -- GET /zones/{zone_id}/co-storage-check
# ---------------------------------------------------------------------------


def test_co_storage_check_returns_200_for_known_zone():
    """Sanity check: the route exists and returns HTTP 200 for Zone_A.

    Problem this test solves: before this PR the route did not exist; any
    GET to this path would have returned 404/405 regardless of zone.
    """
    response = client.get("/zones/Zone_A/co-storage-check", headers=_analyst_token())
    assert response.status_code == 200
    data = response.json()
    assert data["zone_id"] == "Zone_A"
    assert "chemicals" in data
    assert "rules" in data


def test_co_storage_check_chemicals_match_inventory():
    """Zone_B chemical list returned by the route must match the seeded inventory.

    Regression guard: the route builds transactions from the real zone_inventory
    dict loaded at startup -- if that mapping were wrong, the chemical list and
    any mined rules would silently reflect the wrong zone.
    """
    response = client.get("/zones/Zone_B/co-storage-check", headers=_analyst_token())
    assert response.status_code == 200
    data = response.json()
    # DEFAULT_ZONE_INVENTORY["Zone_B"] = ["Sodium hydroxide", "Hydrochloric acid", "Sulfuric acid"]
    assert set(data["chemicals"]) == {
        "Sodium hydroxide",
        "Hydrochloric acid",
        "Sulfuric acid",
    }


def test_co_storage_check_flags_real_incompatible_pair_in_zone_b():
    """Zone_B contains Sodium Hydroxide and Sulfuric Acid -- a pair that appears
    in KNOWN_INCOMPATIBLE_PAIRS with a VIOLENT REACTION note derived from the
    real corpus (sodium hydroxide SDS Section 10, corpus/raw/).

    This is the core Item 1 requirement: 'Add a test proving a real incompatible
    pair in the current inventory gets flagged.'

    Zone_B seed chemicals: Sodium hydroxide, Hydrochloric acid, Sulfuric acid.
    The CAMEO dict key is frozenset(["Sodium Hydroxide", "Sulfuric Acid"]).
    The seeded inventory uses 'Sodium hydroxide' (lowercase h) while the CAMEO
    key uses title-case 'Sodium Hydroxide'. Both spellings appear in the seed
    data as stored -- if casing ever diverges, this test will fail with an empty
    rules list and the fix is to align the casing in zone_inventory.py with the
    keys in apriori_discovery.KNOWN_INCOMPATIBLE_PAIRS.
    """
    response = client.get("/zones/Zone_B/co-storage-check", headers=_analyst_token())
    assert response.status_code == 200
    data = response.json()
    rules = data["rules"]
    # Find any rule whose incompatibility_status flags the violent reaction
    violent_reaction_rules = [
        r for r in rules if "VIOLENT REACTION" in r["incompatibility_status"]
    ]
    assert len(violent_reaction_rules) > 0, (
        "Expected at least one rule flagging VIOLENT REACTION for "
        "Sodium Hydroxide + Sulfuric Acid in Zone_B, but got no such rule. "
        f"All rules returned: {rules}"
    )


def test_co_storage_check_rules_have_required_fields():
    """Each rule in the response must have all CoStorageRule fields.

    Structural contract test -- if api/models.py CoStorageRule schema or
    the route's dict-to-model conversion ever drops a field, this catches it.
    """
    response = client.get("/zones/Zone_B/co-storage-check", headers=_analyst_token())
    assert response.status_code == 200
    rules = response.json()["rules"]
    for rule in rules:
        assert "antecedents" in rule
        assert "consequents" in rule
        assert "support" in rule
        assert "confidence" in rule
        assert "lift" in rule
        assert "incompatibility_status" in rule


def test_co_storage_check_returns_404_for_unknown_zone():
    """An unknown zone_id must return 404, not an empty-rules 200.

    Shares the 404 contract with GET /zones/{zone_id}.
    """
    response = client.get(
        "/zones/Zone_NONEXISTENT/co-storage-check", headers=_analyst_token()
    )
    assert response.status_code == 404


def test_co_storage_check_accessible_to_viewer():
    """Co-storage check is read-only evidence -- VIEWER role must be allowed.

    Unlike /safety/evaluate and /zones/{zone_id}/telemetry which require
    ANALYST or above, this route does not inject data or trigger evaluations.
    """
    response = client.get("/zones/Zone_A/co-storage-check", headers=_viewer_token())
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Item 2 -- POST /alerts/{alert_id}/narrate
# ---------------------------------------------------------------------------


def _create_warning_alert_and_get_id() -> str:
    """Helper: trigger a WARNING eval to seed an AlertRecord, return its alert_id."""
    headers = _analyst_token()
    client.post(
        "/safety/evaluate",
        json={
            "chemical_name": "Toluene",
            "zone_id": "Zone_B",
            "metric_name": "max_storage_temperature",
            "current_value": 50.0,
            "unit": "C",
        },
        headers=headers,
    )
    alerts = client.get("/alerts", headers=headers).json()["alerts"]
    return alerts[-1]["alert_id"]


def test_narrate_alert_returns_200_with_fallback_explanation():
    """Without MISTRAL_API_KEY set in the test env, the narrator returns a
    deterministic fallback string. The route must still 200 and return the
    correct shape -- the LLM being absent is graceful degradation, not a crash.

    This covers the common CI path where no real API key is present.
    """
    alert_id = _create_warning_alert_and_get_id()
    response = client.post(f"/alerts/{alert_id}/narrate", headers=_analyst_token())
    assert response.status_code == 200
    data = response.json()
    assert data["alert_id"] == alert_id
    assert data["safety_state"] == "WARNING"
    assert isinstance(data["explanation"], str)
    assert len(data["explanation"]) > 0
    assert "WARNING" in data["explanation"]


def test_narrate_alert_safety_state_is_always_warning():
    """safety_state in the response is always the deterministic AlertRecord value
    (WARNING -- only WARNINGs create AlertRecords), never an LLM-produced string.

    Critical safety constraint: even if the LLM produced text containing SAFE,
    the route must return WARNING.
    """
    alert_id = _create_warning_alert_and_get_id()
    response = client.post(f"/alerts/{alert_id}/narrate", headers=_analyst_token())
    assert response.status_code == 200
    assert response.json()["safety_state"] == "WARNING"


def test_narrate_alert_returns_404_for_unknown_alert():
    """An alert_id that was never created must return 404.

    Same contract as /admin/sign-off: the route must not fabricate success for
    an alert that does not exist.
    """
    response = client.post(
        "/alerts/ALT_DOES_NOT_EXIST/narrate", headers=_analyst_token()
    )
    assert response.status_code == 404


def test_narrate_alert_accessible_to_viewer():
    """Narrate is read-only (on-demand LLM explain of an already-decided alert)
    -- VIEWER role must be allowed to call it, same as GET /alerts.
    """
    alert_id = _create_warning_alert_and_get_id()
    response = client.post(f"/alerts/{alert_id}/narrate", headers=_viewer_token())
    assert response.status_code == 200


@patch("api.main.SafetyCardNarrator")
def test_narrate_alert_with_language_calls_translate(mock_narrator_class):
    """When ?language=si is supplied the route must call translate_safety_card
    and include a translation key in the response.

    The LLM client is mocked so this does not require a real API key.
    """
    mock_narrator = MagicMock()
    mock_narrator_class.return_value = mock_narrator
    mock_narrator.explain_alert.return_value = "Mocked explanation."
    mock_narrator.translate_safety_card.return_value = {
        "chemical_name": "Toluene",
        "state": "WARNING",
        "reasoning": "Mocked Sinhala reasoning",
        "citation": "Mocked citation",
    }

    alert_id = _create_warning_alert_and_get_id()
    response = client.post(
        f"/alerts/{alert_id}/narrate?language=si", headers=_analyst_token()
    )
    assert response.status_code == 200
    data = response.json()
    assert data["explanation"] == "Mocked explanation."
    assert data["translation"] is not None
    assert data["translation"]["state"] == "WARNING"
    mock_narrator.translate_safety_card.assert_called_once()
    call_args = mock_narrator.translate_safety_card.call_args
    # language arg can be positional or keyword
    passed_lang = (
        call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("language")
    )
    assert passed_lang == "si"
