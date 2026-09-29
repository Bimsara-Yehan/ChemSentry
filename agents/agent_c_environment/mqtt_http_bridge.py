"""MQTT -> HTTP bridge: forwards real sensor readings to the live API (M4).

Problem this solves: the Live Environment tab's zone state
(`api/main.py`'s `_LATEST_ZONE_EVALUATIONS`) is an in-memory cache local to
the running API process, updated only by `POST /zones/{zone_id}/telemetry`.
A standalone `MqttEnvironmentSubscriber` (mqtt_subscriber.py) running as its
own OS process cannot reach into that cache -- it's a different process's
memory. `POST /zones/{zone_id}/telemetry`'s own docstring already anticipated
this gap ("any future hardware bridge that prefers HTTP over MQTT"): this
module is that bridge. It does no evaluation itself -- it only parses each
MQTT message into a `SensorReading` and forwards it to the real API, so the
exact same code path (evaluation, in-memory cache update, alert persistence)
runs whether a reading arrives via the UI's simulator button or a real
ESP32's MQTT publish.

Run alongside `uvicorn api.main:app` and `docker compose up` (Mosquitto):
    python -m agents.agent_c_environment.mqtt_http_bridge \\
        --mqtt-ca-certs firmware/certs/ca.crt.pem \\
        --mqtt-certfile firmware/certs/agent_c_bridge.crt.pem \\
        --mqtt-keyfile firmware/certs/agent_c_bridge.key.pem \\
        --api-base http://localhost:8000 \\
        --username analyst_user --password analyst123
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import paho.mqtt.client as mqtt
import requests

from agents.agent_c_environment.mqtt_subscriber import (
    TOPIC_WILDCARD,
    parse_reading,
    zone_id_from_topic,
)

logger = logging.getLogger(__name__)


def build_forward_request(
    api_base: str, topic: str, payload: bytes | str
) -> tuple[str, dict] | None:
    """Given one raw MQTT message, build the (url, json_body) to forward to the
    API -- pure, no I/O, so testable without a live broker or API.

    The URL's zone comes from the *payload*, not the topic: unlike
    mqtt_subscriber.py's evaluate_raw_message (which just logs a mismatch and
    proceeds), POST /zones/{zone_id}/telemetry itself 400s if the path zone_id
    and body zone_id disagree, so building the URL from the topic would let a
    mismatched message trip that rejection for no reason. Using the payload's
    own zone_id for both keeps url and body self-consistent by construction.
    zone_id_from_topic is still used as a coarse filter, so a message on a
    completely unrelated (non-chemsentry) topic is ignored rather than
    forwarded anywhere.

    None (rather than raising) for an unrecognised topic or a payload that
    fails SensorReading validation, matching evaluate_raw_message's fail-soft
    contract -- one bad device's message must not take the bridge down.
    """
    if zone_id_from_topic(topic) is None:
        return None
    reading = parse_reading(payload)
    if reading is None:
        return None
    url = f"{api_base.rstrip('/')}/zones/{reading.zone_id}/telemetry"
    return url, reading.model_dump(mode="json")


class MqttHttpBridge:
    """Subscribes to real sensor telemetry and forwards each reading to the
    live API over HTTP, authenticated once at startup."""

    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        mqtt_ca_certs: str | Path,
        mqtt_certfile: str | Path,
        mqtt_keyfile: str | Path,
        api_base: str,
        username: str,
        password: str,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._token = self._login(username, password)

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="chemsentry-agent-c-bridge",
        )
        self._client.tls_set(
            ca_certs=str(mqtt_ca_certs),
            certfile=str(mqtt_certfile),
            keyfile=str(mqtt_keyfile),
        )
        self._client.on_connect = self._handle_connect
        self._client.on_message = self._handle_message
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port

    def _login(self, username: str, password: str) -> str:
        """Get an API token once at startup (short-lived bridge process;
        no refresh logic -- restart the bridge if a demo runs past token
        expiry, matching this project's other single-shot dev scripts)."""
        response = requests.post(
            f"{self._api_base}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _handle_connect(
        self, client, userdata, flags, reason_code, properties=None
    ) -> None:
        logger.info("Bridge connected to broker (rc=%s)", reason_code)
        client.subscribe(TOPIC_WILDCARD)

    def _handle_message(self, client, userdata, msg) -> None:
        result = build_forward_request(self._api_base, msg.topic, msg.payload)
        if result is None:
            logger.warning("Ignoring unrecognised/malformed message on %s", msg.topic)
            return
        url, body = result

        try:
            response = requests.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10,
            )
            response.raise_for_status()
            logger.info(
                "Forwarded %s: %.1f C -> safety_state=%s",
                body["zone_id"],
                body["temperature_celsius"],
                response.json().get("safety_state"),
            )
        except requests.RequestException as exc:
            logger.error(
                "Failed to forward reading for %s to the API: %s", body["zone_id"], exc
            )

    def run_forever(self) -> None:
        self._client.connect(self._mqtt_host, self._mqtt_port)
        self._client.loop_forever()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=8883)
    parser.add_argument("--mqtt-ca-certs", default="firmware/certs/ca.crt.pem")
    parser.add_argument(
        "--mqtt-certfile", default="firmware/certs/agent_c_bridge.crt.pem"
    )
    parser.add_argument(
        "--mqtt-keyfile", default="firmware/certs/agent_c_bridge.key.pem"
    )
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--username", default="analyst_user")
    parser.add_argument("--password", default="analyst123")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args = _parse_args()
    bridge = MqttHttpBridge(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_ca_certs=args.mqtt_ca_certs,
        mqtt_certfile=args.mqtt_certfile,
        mqtt_keyfile=args.mqtt_keyfile,
        api_base=args.api_base,
        username=args.username,
        password=args.password,
    )
    logger.info(
        "Bridge logged in; connecting to broker %s:%s", args.mqtt_host, args.mqtt_port
    )
    bridge.run_forever()


if __name__ == "__main__":
    main()
