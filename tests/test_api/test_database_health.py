"""Unit tests for api/database.py's health-check helpers (M4).

check_mqtt_broker_health() replaced a hardcoded "ok" in GET /health -- proving
it actually reflects reachability needs a real listening socket and a real
closed port, not a mock of the function under test.
"""

import socket
import threading

from api.database import check_mqtt_broker_health


def test_reports_ok_when_something_is_actually_listening(monkeypatch):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    # Accept (and ignore) one connection so the server socket doesn't matter
    # for the check itself -- check_mqtt_broker_health only needs the TCP
    # handshake to succeed, not an MQTT or TLS conversation.
    threading.Thread(target=lambda: server.accept(), daemon=True).start()

    monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("MQTT_PORT", str(port))
    try:
        assert check_mqtt_broker_health() == "ok"
    finally:
        server.close()


def test_reports_error_when_nothing_is_listening(monkeypatch):
    # Bind and immediately close -- this reserves a port a moment ago that is
    # now guaranteed to have nothing listening on it, unlike a hardcoded
    # arbitrary port number which another process could legitimately own.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("MQTT_PORT", str(free_port))
    result = check_mqtt_broker_health(timeout_seconds=0.5)
    assert result.startswith("error:")


def test_reports_error_on_unreachable_host(monkeypatch):
    """A non-routable address (TEST-NET-1, RFC 5737) must time out as an
    error, not hang the health check or raise past the function boundary."""
    monkeypatch.setenv("MQTT_HOST", "192.0.2.1")
    monkeypatch.setenv("MQTT_PORT", "8883")
    result = check_mqtt_broker_health(timeout_seconds=0.5)
    assert result.startswith("error:")
