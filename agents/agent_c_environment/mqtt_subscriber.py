"""MQTT subscriber wrapper for Agent C (M4).

Thin, real-I/O adapter around `EnvironmentalMonitor` (monitor.py): parses
incoming sensor telemetry off the broker into a `SensorReading` and hands it
to the DB-free monitor core, then hands any excursion to an injected
callback (persistence into `AlertRecord`/`AuditLogRecord` -- see
`api/db_models.py` -- is deliberately not this module's job, so this class
stays testable without a live broker or database).

Topic scheme (not previously defined anywhere in this repo -- confirmed by
grep before adding this): one topic per zone,
`chemsentry/sensors/<zone_id>/reading`, JSON payload matching
`api.models.SensorReading`'s fields exactly. `simulator/telemetry_simulator.py`
publishes to this same scheme, standing in for real ESP32 firmware (plan
§16), which does not yet publish at all (firmware/src/main.cpp reads the
DHT22 but has no MQTT publish call -- a separate, tracked gap, not one this
module works around).

TLS is mandatory, matching `firmware/mosquitto.conf`'s
`require_certificate true` -- there is no plaintext fallback path here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from agents.agent_c_environment.monitor import EnvironmentalMonitor, ZoneEvaluation
from api.models import SensorReading

logger = logging.getLogger(__name__)

TOPIC_WILDCARD = "chemsentry/sensors/+/reading"


def topic_for_zone(zone_id: str) -> str:
    """The single topic a given zone's readings are published/subscribed on."""
    return f"chemsentry/sensors/{zone_id}/reading"


def zone_id_from_topic(topic: str) -> str | None:
    """Extract `<zone_id>` from a `chemsentry/sensors/<zone_id>/reading` topic.

    Returns None for anything not matching the scheme, rather than raising --
    a malformed/foreign topic on the same broker must not crash the
    subscriber; see `parse_reading` for the same fail-soft treatment of a bad
    payload.
    """
    parts = topic.split("/")
    if (
        len(parts) == 4
        and parts[0] == "chemsentry"
        and parts[1] == "sensors"
        and parts[3] == "reading"
    ):
        return parts[2]
    return None


def parse_reading(payload: bytes | str) -> SensorReading | None:
    """Parse a raw MQTT payload into a `SensorReading`.

    Returns None (rather than raising) on malformed JSON or a payload that
    fails `SensorReading`'s validation (e.g. a temperature outside the DHT22
    range) -- one bad reading from one device must not take the whole
    subscriber down; it is logged and dropped.
    """
    try:
        data = json.loads(payload)
        return SensorReading(**data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        logger.warning("Dropping malformed sensor reading payload: %s", exc)
        return None


def evaluate_raw_message(
    monitor: EnvironmentalMonitor,
    topic: str,
    payload: bytes | str,
    on_excursion: Callable[[ZoneEvaluation], None] | None = None,
) -> ZoneEvaluation | None:
    """Parse one raw MQTT message and run it through the monitor.

    Free function (not a method) precisely so it's testable without
    constructing `MqttEnvironmentSubscriber` -- that class's constructor
    eagerly calls `tls_set()` against real certificate files that don't
    exist in CI. `MqttEnvironmentSubscriber._handle_message` below is a thin
    wrapper around this; unit tests call this directly instead.

    Returns None if the topic doesn't match the expected scheme or the
    payload is malformed/fails validation; otherwise the resulting
    `ZoneEvaluation`, after invoking `on_excursion` if it is a real
    excursion.
    """
    zone_id = zone_id_from_topic(topic)
    if zone_id is None:
        logger.warning("Ignoring message on unrecognised topic: %s", topic)
        return None

    reading = parse_reading(payload)
    if reading is None:
        return None
    if reading.zone_id != zone_id:
        logger.warning(
            "Topic zone '%s' does not match payload zone '%s'; using payload zone_id",
            zone_id,
            reading.zone_id,
        )

    evaluation = monitor.handle_reading(reading)
    if evaluation.is_excursion and on_excursion is not None:
        on_excursion(evaluation)
    return evaluation


class MqttEnvironmentSubscriber:
    """Subscribes to zone telemetry and drives `EnvironmentalMonitor` from it.

    Example:
        >>> subscriber = MqttEnvironmentSubscriber(
        ...     monitor, host="localhost", port=8883,
        ...     ca_certs="firmware/certs/ca.crt.pem",
        ...     certfile="firmware/certs/device1.crt.pem",
        ...     keyfile="firmware/certs/device1.key.pem",
        ...     on_excursion=persist_alert,
        ... )
        >>> subscriber.connect_and_loop_forever()
    """

    def __init__(
        self,
        monitor: EnvironmentalMonitor,
        host: str,
        port: int,
        ca_certs: str | Path,
        certfile: str | Path,
        keyfile: str | Path,
        client_id: str = "chemsentry-agent-c",
        on_excursion: Callable[[ZoneEvaluation], None] | None = None,
    ) -> None:
        """
        Args:
            monitor: The DB-free core monitor -- this class's only job is to
                get real MQTT bytes into `monitor.handle_reading()`.
            host, port: Broker address (docker-compose's mosquitto service).
            ca_certs, certfile, keyfile: TLS material -- see
                firmware/certs/README.md for how these are generated locally;
                required, matching mosquitto.conf's `require_certificate true`.
            on_excursion: Called with every `ZoneEvaluation` whose
                `is_excursion` is True. Left as an injected callback (not a
                hardcoded DB write) so this class has no database dependency
                of its own; wire it to alert persistence at the call site.
        """
        self._monitor = monitor
        self._host = host
        self._port = port
        self._on_excursion = on_excursion

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._client.tls_set(
            ca_certs=str(ca_certs), certfile=str(certfile), keyfile=str(keyfile)
        )
        self._client.on_connect = self._handle_connect
        self._client.on_message = self._handle_message

    def connect_and_loop_forever(self) -> None:
        """Connect to the broker and block, dispatching messages forever."""
        self._client.connect(self._host, self._port)
        self._client.loop_forever()

    def disconnect(self) -> None:
        self._client.disconnect()

    def _handle_connect(
        self, client, userdata, flags, reason_code, properties=None
    ) -> None:
        client.subscribe(TOPIC_WILDCARD)
        logger.info("Agent C subscribed to %s", TOPIC_WILDCARD)

    def _handle_message(self, client, userdata, msg) -> None:
        """paho's on_message callback -- delegates to `evaluate_raw_message`,
        the free function unit tests exercise directly."""
        self.handle_raw_message(msg.topic, msg.payload)

    def handle_raw_message(
        self, topic: str, payload: bytes | str
    ) -> ZoneEvaluation | None:
        """Parse and evaluate one message; returns None if the message was
        malformed or the topic didn't match the expected scheme."""
        return evaluate_raw_message(self._monitor, topic, payload, self._on_excursion)
