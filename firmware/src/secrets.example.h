// Template for firmware/src/secrets.h -- copy this file to secrets.h (which
// is gitignored, see .gitignore) and fill in real values. secrets.h is
// #include-d by main.cpp; without it the firmware will not compile, which is
// intentional -- it forces every device builder to provide their own local
// WiFi credentials and TLS material rather than share one hardcoded set.
//
// Never fill these placeholder values in here and commit this file --
// this .example.h file IS committed, secrets.h is not.

#pragma once

// --- WiFi ---
#define SECRET_WIFI_SSID "your-network-name"
#define SECRET_WIFI_PASSWORD "your-network-password"

// --- MQTT broker ---
// The dev machine's LAN/hotspot IP running `docker compose up` (mosquitto).
// Re-check with `ipconfig` (Windows) / `ip addr` (Linux/Mac) whenever the
// network changes -- an ESP32 on WiFi cannot reach "localhost", that always
// means the ESP32 itself.
#define SECRET_MQTT_HOST "192.168.1.100"
#define SECRET_MQTT_PORT 8883

// --- TLS material ---
// Generate with (from repo root):
//   python firmware/generate_certs.py --out firmware/certs --devices <device> \
//       --server-san <this machine's LAN IP>
// then paste the contents of the generated PEM files below verbatim,
// including the BEGIN/END lines. ca.crt.pem is the same for every device on
// one broker; <device>.crt.pem / <device>.key.pem must match the device
// common name you generated (e.g. "zone_c").
//
// These must be real `const char*` variables, not #define macros: the C
// preprocessor only takes a macro body from the #define's own line, so a
// multi-line R"EOF(...)EOF" raw string placed after #define NAME silently
// breaks -- everything past the first line falls out of the macro and
// becomes stray top-level text that fails to compile.
static const char *SECRET_CA_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
paste firmware/certs/ca.crt.pem here
-----END CERTIFICATE-----
)EOF";

static const char *SECRET_CLIENT_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
paste firmware/certs/<device>.crt.pem here
-----END CERTIFICATE-----
)EOF";

static const char *SECRET_CLIENT_KEY = R"EOF(
-----BEGIN RSA PRIVATE KEY-----
paste firmware/certs/<device>.key.pem here
-----END RSA PRIVATE KEY-----
)EOF";
