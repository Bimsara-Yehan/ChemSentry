# TLS Certificates (not committed)

Generate a local CA plus a broker cert/key (`ca.crt`, `server.crt`, `server.key`) and one
client cert per device before running `docker compose up`. Everything in this directory
except this file and `.gitkeep` is gitignored -- see `.gitignore` and `mosquitto.conf` in
the parent directory.
