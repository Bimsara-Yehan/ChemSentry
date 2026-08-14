# Firmware -- ESP32 (M4)

PlatformIO project: ESP32 + DHT22 sensor nodes publishing over MQTT/TLS. Not yet scaffolded
-- run `pio init` here once hardware arrives (Week 3, see `setup.md` Section 4).

TLS certificates for the broker and devices live in `certs/` (gitignored -- generate locally
with a local CA, never commit private keys).
