"""Unit tests for the MQTT->HTTP bridge's message-routing logic (M4).

`MqttHttpBridge` itself is not exercised here -- its constructor eagerly logs
in over HTTP and opens a real TLS MQTT connection, neither of which has a
place in CI. `build_forward_request` is the pure, I/O-free part: given a raw
topic + payload, what URL and body would be forwarded. Mirrors how
tests/test_agent_c/test_mqtt_subscriber.py tests evaluate_raw_message instead
of MqttEnvironmentSubscriber.
"""

from agents.agent_c_environment.mqtt_http_bridge import build_forward_request


def test_valid_reading_builds_the_expected_zone_telemetry_request() -> None:
    payload = (
        '{"zone_id": "Zone_C", "temperature_celsius": 18.0, '
        '"humidity_percent": 40.0, "timestamp": "2026-01-01T00:00:00Z", '
        '"device_id": "8C:94:DF:AA:4A:6C"}'
    )
    result = build_forward_request(
        "http://localhost:8000", "chemsentry/sensors/Zone_C/reading", payload
    )
    assert result is not None
    url, body = result
    assert url == "http://localhost:8000/zones/Zone_C/telemetry"
    assert body["zone_id"] == "Zone_C"
    assert body["temperature_celsius"] == 18.0
    assert body["device_id"] == "8C:94:DF:AA:4A:6C"


def test_api_base_trailing_slash_does_not_produce_a_double_slash_url() -> None:
    payload = (
        '{"zone_id": "Zone_A", "temperature_celsius": 20.0, '
        '"humidity_percent": 45.0, "timestamp": "2026-01-01T00:00:00Z", '
        '"device_id": "device1"}'
    )
    result = build_forward_request(
        "http://localhost:8000/", "chemsentry/sensors/Zone_A/reading", payload
    )
    assert result is not None
    url, _ = result
    assert url == "http://localhost:8000/zones/Zone_A/telemetry"


def test_unrecognised_topic_is_ignored_not_raised() -> None:
    assert (
        build_forward_request("http://localhost:8000", "some/other/topic", "{}") is None
    )


def test_malformed_payload_is_ignored_not_raised() -> None:
    result = build_forward_request(
        "http://localhost:8000", "chemsentry/sensors/Zone_C/reading", "not json"
    )
    assert result is None


def test_payload_failing_schema_validation_is_ignored() -> None:
    """temperature_celsius outside the DHT22 range (-40..80) must fail
    SensorReading validation, the same fail-soft contract as
    mqtt_subscriber.py's parse_reading."""
    payload = (
        '{"zone_id": "Zone_C", "temperature_celsius": 999.0, '
        '"humidity_percent": 40.0, "timestamp": "2026-01-01T00:00:00Z", '
        '"device_id": "device1"}'
    )
    result = build_forward_request(
        "http://localhost:8000", "chemsentry/sensors/Zone_C/reading", payload
    )
    assert result is None


def test_topic_zone_mismatch_builds_a_url_that_matches_the_payload_zone() -> None:
    """POST /zones/{zone_id}/telemetry 400s if the path zone and body zone
    disagree (api/main.py: 'Path zone_id ... does not match reading.zone_id').
    The URL must therefore come from the payload's own zone_id, not the
    topic's -- otherwise a mismatched message would trip that rejection for
    no reason. zone_id_from_topic is only a coarse "is this a chemsentry
    sensor topic" filter here, not the source of the URL's zone."""
    payload = (
        '{"zone_id": "Zone_B", "temperature_celsius": 20.0, '
        '"humidity_percent": 45.0, "timestamp": "2026-01-01T00:00:00Z", '
        '"device_id": "device1"}'
    )
    result = build_forward_request(
        "http://localhost:8000", "chemsentry/sensors/Zone_A/reading", payload
    )
    assert result is not None
    url, body = result
    assert url == "http://localhost:8000/zones/Zone_B/telemetry"
    assert body["zone_id"] == "Zone_B"
