"""API route tests for Agent B items wired in PR 1, PR 2 & PR 3 (M3).

Tests:
  - GET /zones/{zone_id}/co-storage-check  (Item 1: co-storage / CAMEO warnings)
  - POST /alerts/{alert_id}/narrate         (Item 2: plain-language safety card)
  - POST /classifier/severity               (Item 3: hazard severity classifier)
  - POST /query/open                        (Item 4: open-ended query orchestrator)

All tests use the shared TestClient from test_api_gateway.py which already
sets up the fixture retriever and the isolated test database via conftest.py.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import api.main as main
from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from extraction.models import SDSMetadata
from extraction.pipeline import extract_document

# In standalone test runs, main.retriever is empty (corpus/raw/ is gitignored).
# Seed a minimal fixture doc so /safety/evaluate can produce genuine WARNINGs for Toluene.
if main.retriever is None or len(getattr(main.retriever, "documents", [])) == 0:
    _toluene_doc = extract_document(
        "SECTION 7: Handling and storage\nStore below 25 C.\n",
        SDSMetadata(
            document_id="TEST_TOL_001",
            chemical_name="Toluene",
            supplier="ABC Chemicals",
            retrieval_date=date.today(),
        ),
    )
    main.retriever = CorpusRetriever([_toluene_doc])

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


# ---------------------------------------------------------------------------
# Item 3 -- POST /classifier/severity
# ---------------------------------------------------------------------------


def test_classify_severity_returns_200_with_expected_fields():
    """Valid severity classification request returns 200 with severity, confidence,
    and the documented data gap note explaining that NFPA ratings are caller-supplied.
    """
    response = client.post(
        "/classifier/severity",
        json={
            "chemical_name": "Ethanol",
            "nfpa_health": 2,
            "nfpa_flammability": 3,
            "nfpa_instability": 0,
            "ghs_code_count": 2,
        },
        headers=_analyst_token(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["chemical_name"] == "Ethanol"
    assert data["severity"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["nfpa_health"] == 2
    assert data["nfpa_flammability"] == 3
    assert data["nfpa_instability"] == 0
    assert data["ghs_code_count"] == 2
    assert "caller-supplied" in data["note"]


def test_classify_severity_predicts_critical_for_high_hazard_ratings():
    """Extreme ratings (4/4/3 with 7 GHS codes) must classify as CRITICAL.

    Validates that the classifier output aligns with the underlying decision tree model.
    """
    response = client.post(
        "/classifier/severity",
        json={
            "chemical_name": "Nitroglycerin",
            "nfpa_health": 4,
            "nfpa_flammability": 4,
            "nfpa_instability": 3,
            "ghs_code_count": 7,
        },
        headers=_analyst_token(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["severity"] == "CRITICAL"


def test_classify_severity_requires_all_nfpa_fields_validation_error():
    """Omitting NFPA fields must return 422 Unprocessable Entity.

    Regression guard for the NFPA data gap decision: we explicitly chose option (b)
    (caller-supplied required fields) rather than silently defaulting to 0, so that
    the caller cannot unknowingly receive a severity label derived from fabricated zeros.
    """
    response = client.post(
        "/classifier/severity",
        json={
            "chemical_name": "Ethanol",
            "ghs_code_count": 2,
        },
        headers=_analyst_token(),
    )
    assert response.status_code == 422


def test_classify_severity_accessible_to_viewer():
    """Severity classification is a read-only calculation, accessible to VIEWER role."""
    response = client.post(
        "/classifier/severity",
        json={
            "chemical_name": "Water",
            "nfpa_health": 0,
            "nfpa_flammability": 0,
            "nfpa_instability": 0,
            "ghs_code_count": 0,
        },
        headers=_viewer_token(),
    )
    assert response.status_code == 200
    assert response.json()["severity"] == "LOW"


def test_classify_severity_requires_auth():
    """Unauthenticated call to /classifier/severity must return 401."""
    response = client.post(
        "/classifier/severity",
        json={
            "chemical_name": "Ethanol",
            "nfpa_health": 2,
            "nfpa_flammability": 3,
            "nfpa_instability": 0,
            "ghs_code_count": 2,
        },
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Item 4 -- POST /query/open
# ---------------------------------------------------------------------------


def test_query_open_returns_200_with_fallback_when_no_api_key():
    """When MISTRAL_API_KEY is not set (e.g. CI / local test environment),
    the endpoint gracefully returns 200 with the orchestrator fallback string
    and lists all registered tools.
    """
    response = client.post(
        "/query/open",
        json={"query": "Why did Zone B alert?"},
        headers=_analyst_token(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Why did Zone B alert?"
    assert "FALLBACK: Unable to orchestrate query dynamically" in data["response"]
    expected_tools = {
        "search_sds_thresholds",
        "get_recent_alerts",
        "check_zone_co_storage",
    }
    assert set(data["tools_registered"]) == expected_tools


def test_query_open_registered_tool_search_sds_thresholds():
    """Directly test the registered search_sds_thresholds tool function.

    Exercises the real CorpusRetriever bound in api.main against the fixture
    corpus (Toluene doc). Proves the tool retrieves real thresholds and citations.
    """
    orchestrator = main._get_query_orchestrator()
    tool_func = orchestrator._tools["search_sds_thresholds"]

    # Known chemical in fixture corpus
    result = tool_func(chemical_name="Toluene")
    assert "Toluene" in result
    assert "max_storage_temperature" in result
    assert "25.0 C" in result
    assert "TEST_TOL_001" in result

    # Unknown chemical
    empty_result = tool_func(chemical_name="UnknownChem")
    assert "No SDS thresholds found" in empty_result


def test_query_open_registered_tool_get_recent_alerts():
    """Directly test the registered get_recent_alerts tool function.

    Seeds a warning alert and verifies the tool retrieves it from the audit DB.
    """
    alert_id = _create_warning_alert_and_get_id()
    orchestrator = main._get_query_orchestrator()
    tool_func = orchestrator._tools["get_recent_alerts"]

    # General query
    result = tool_func(zone_id=None, limit=5)
    assert alert_id in result
    assert "Zone_B" in result

    # Filtered by zone
    zone_result = tool_func(zone_id="Zone_B", limit=5)
    assert alert_id in zone_result

    # Non-existent zone
    empty_result = tool_func(zone_id="Zone_Nonexistent", limit=5)
    assert "No recent alerts found" in empty_result


def test_query_open_registered_tool_check_zone_co_storage():
    """Directly test the registered check_zone_co_storage tool function.

    Proves the tool analyzes Zone_B chemicals and reports the CAMEO violent
    reaction warning for Sodium hydroxide + Sulfuric acid.
    """
    orchestrator = main._get_query_orchestrator()
    tool_func = orchestrator._tools["check_zone_co_storage"]

    result = tool_func(zone_id="Zone_B")
    assert "VIOLENT REACTION" in result
    assert "Sodium hydroxide" in result
    assert "Sulfuric acid" in result

    # Non-existent zone
    not_found = tool_func(zone_id="Zone_Missing")
    assert "not found in inventory" in not_found


def test_query_open_accessible_to_viewer():
    """POST /query/open is a read-only research endpoint accessible to VIEWER."""
    response = client.post(
        "/query/open",
        json={"query": "What are the storage guidelines for zone A?"},
        headers=_viewer_token(),
    )
    assert response.status_code == 200


def test_query_open_requires_auth():
    """Unauthenticated call to /query/open must return 401."""
    response = client.post(
        "/query/open",
        json={"query": "Test query without auth"},
    )
    assert response.status_code == 401


def test_query_open_validates_non_empty_query():
    """Empty query string must return 422 validation error."""
    response = client.post(
        "/query/open",
        json={"query": ""},
        headers=_analyst_token(),
    )
    assert response.status_code == 422
