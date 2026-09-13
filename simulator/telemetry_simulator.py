"""Sensor telemetry simulator -- stands in for real ESP32/DHT22 firmware (M4).

Plan §16 requires a demo-safe way to exercise the full sensor -> Agent C ->
Agent A -> Deterministic Safety Layer chain without physical hardware.
`firmware/src/main.cpp` reads a real DHT22 but has no MQTT publish call yet
(a separate, tracked gap) -- this module's whole job is to stand in for
that missing publish step, using the exact same topic scheme and payload
shape `agents/agent_c_environment/mqtt_subscriber.py` expects
(`chemsentry/sensors/<zone_id>/reading`, JSON matching `api.models.SensorReading`).

Honesty note (why "excursion mode" doesn't guarantee a WARNING): this
simulator can only *push an extreme sensor value* -- it cannot manufacture a
safety threshold that doesn't exist. Per zone_inventory.py's seed-data
comment, only Zone_C (hydrogen peroxide solution) has a real, extracted
numeric storage-temperature range anywhere in this corpus (2.0-8.0 C).
Pushing an extreme reading for Zone_A or Zone_B will correctly still
evaluate to UNKNOWN -- there is no versioned threshold for the deterministic
safety layer to compare against, and it must not invent one. That is the
central principle working as designed, not a limitation of this simulator.
"""

from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import paho.mqtt.client as mqtt

from agents.agent_c_environment.mqtt_subscriber import topic_for_zone
from api.models import SensorReading

logger = logging.getLogger(__name__)

# Plausible ambient warehouse conditions -- not sourced from any SDS (this is
# simulated *environment*, not a retrieved chemical property), used only for
# steady-state demo readings.
_STEADY_TEMP_RANGE_C = (18.0, 24.0)
_STEADY_HUMIDITY_RANGE_PCT = (40.0, 55.0)

# Deliberately outside Zone_C's real retrieved range (2.0-8.0 C) so excursion
# mode against Zone_C reliably produces a genuine, evidence-backed WARNING
# rather than relying on random chance.
_EXCURSION_TEMP_C = 18.0

Mode = Literal["steady", "excursion"]


def generate_reading(zone_id: str, mode: Mode, device_id: str) -> SensorReading:
    """Produce one plausible sensor reading for a zone.

    Args:
        zone_id: Target zone (must match a topic Agent C subscribes to).
        mode: "steady" for a normal ambient reading; "excursion" for a
            reading deliberately outside the plausible range, to demo the
            WARNING path (see module docstring for why this only reliably
            triggers a real WARNING in a zone with a real extracted
            threshold, i.e. Zone_C in this corpus).
        device_id: Simulated ESP32 identifier.
    """
    humidity = round(random.uniform(*_STEADY_HUMIDITY_RANGE_PCT), 1)
    if mode == "steady":
        temperature = round(random.uniform(*_STEADY_TEMP_RANGE_C), 1)
    else:
        temperature = _EXCURSION_TEMP_C

    return SensorReading(
        zone_id=zone_id,
        temperature_celsius=temperature,
        humidity_percent=humidity,
        timestamp=datetime.now(timezone.utc),
        device_id=device_id,
    )


class TelemetryPublisher:
    """Publishes simulated `SensorReading`s over MQTT/TLS, one zone loop at a time.

    Mirrors `MqttEnvironmentSubscriber`'s TLS setup exactly (mandatory client
    cert, matching `firmware/mosquitto.conf`'s `require_certificate true`) --
    a simulated device must authenticate the same way a real one would, not
    take a shortcut real firmware couldn't.
    """

    def __init__(
        self,
        host: str,
        port: int,
        ca_certs: str | Path,
        certfile: str | Path,
        keyfile: str | Path,
        device_id: str = "simulator-device1",
    ) -> None:
        self._device_id = device_id
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=device_id,
        )
        self._client.tls_set(
            ca_certs=str(ca_certs), certfile=str(certfile), keyfile=str(keyfile)
        )
        self._client.connect(host, port)

    def publish_reading(self, reading: SensorReading) -> None:
        payload = reading.model_dump_json()
        self._client.publish(topic_for_zone(reading.zone_id), payload)
        logger.info(
            "Published %s: %.1f C", reading.zone_id, reading.temperature_celsius
        )

    def run(
        self,
        zone_ids: list[str],
        mode: Mode,
        interval_seconds: float,
        iterations: int | None = None,
    ) -> None:
        """Publish one reading per zone every `interval_seconds`.

        Args:
            iterations: Number of rounds to publish; None runs forever
                (Ctrl-C to stop), for an unattended live demo.
        """
        count = 0
        while iterations is None or count < iterations:
            for zone_id in zone_ids:
                reading = generate_reading(zone_id, mode, self._device_id)
                self.publish_reading(reading)
            count += 1
            if iterations is None or count < iterations:
                time.sleep(interval_seconds)

    def disconnect(self) -> None:
        self._client.disconnect()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--ca-certs", default="firmware/certs/ca.crt.pem")
    parser.add_argument("--certfile", default="firmware/certs/device1.crt.pem")
    parser.add_argument("--keyfile", default="firmware/certs/device1.key.pem")
    parser.add_argument(
        "--zones",
        nargs="+",
        default=["Zone_A", "Zone_B", "Zone_C"],
        help="Zone IDs to publish readings for (must match Agent C's inventory).",
    )
    parser.add_argument("--mode", choices=["steady", "excursion"], default="steady")
    parser.add_argument(
        "--interval", type=float, default=5.0, help="Seconds between rounds."
    )
    parser.add_argument(
        "--count", type=int, default=None, help="Number of rounds; omit to run forever."
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    publisher = TelemetryPublisher(
        host=args.host,
        port=args.port,
        ca_certs=args.ca_certs,
        certfile=args.certfile,
        keyfile=args.keyfile,
    )
    try:
        publisher.run(args.zones, args.mode, args.interval, args.count)
    finally:
        publisher.disconnect()


if __name__ == "__main__":
    main()
