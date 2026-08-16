# TLS Certificates (not committed)

Generate a local CA plus a broker cert/key (`ca.crt`, `server.crt`, `server.key`) and one
client cert per device before running `docker compose up`. Everything in this directory
except this file and `.gitkeep` is gitignored -- see `.gitignore` and `mosquitto.conf` in
the parent directory.

This repo includes a helper cert generator at `firmware/generate_certs.py` and a
PowerShell wrapper `firmware/generate_certs.ps1` to make development easier.

Quick usage (from repo root):

PowerShell (recommended on Windows):
```powershell
.\firmware\generate_certs.ps1 -OutDir .\firmware\certs -Devices device1,device2
```

Or use the Python script directly (works cross-platform):
```powershell
.venv-3.11\Scripts\Activate.ps1
python firmware\generate_certs.py --out firmware\certs --devices device1,device2
```

Generated files:
- `ca.key.pem` (private CA key — keep secret)
- `ca.crt.pem` (CA certificate)
- `server.key.pem` / `server.crt.pem` (broker key/cert)
- `<device>.key.pem` / `<device>.crt.pem` (one pair per device common name)

Notes:
- The CA and certs are for local development only. Do not use these in production.
- The folder is intentionally gitignored; check `firmware/certs/.gitignore` and
	`firmware/mosquitto.conf` for placement expectations.
