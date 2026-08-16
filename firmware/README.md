# Firmware — ESP32 (PlatformIO)

This folder contains a minimal PlatformIO project to test ESP32 uploads and the
serial monitor. It implements a simple LED blink sketch on the board's built-in
LED.

How to use (VS Code PlatformIO):

1. Install the PlatformIO extension in VS Code (already done).
2. Open the project in VS Code.
3. Connect your ESP32 board via a data-capable USB cable.
4. Select the `PlatformIO` icon, then `Project Tasks` → `esp32dev` → `Upload`.
5. Open `PlatformIO` → `Serial Monitor` to view debug output at 115200 baud.

CLI alternative (PlatformIO must be installed):

```powershell
# build
platformio run -d firmware

# upload (auto-detects port)
platformio run -d firmware -t upload

# monitor
platformio device monitor -d firmware --port COM3 --baud 115200
```

Replace `COM3` with your board's serial port on Windows.
# Firmware -- ESP32 (M4)

PlatformIO project: ESP32 + DHT22 sensor nodes publishing over MQTT/TLS. Not yet scaffolded
-- run `pio init` here once hardware arrives (Week 3, see `setup.md` Section 4).

TLS certificates for the broker and devices live in `certs/` (gitignored -- generate locally
with a local CA, never commit private keys).
