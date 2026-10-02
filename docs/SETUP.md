# Local setup

Use Python 3.11 (tested 3.11.8), Docker Desktop/Compose, and Node 22 for the frontend.
The clean Python environment uses `requirements.lock.txt`; the local project is
installed separately so the lock contains no private repository URLs or machine paths.

macOS/Linux:
```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python scripts/start.py infra
.venv/bin/python scripts/start.py prepare
.venv/bin/python scripts/start.py api
```
Windows PowerShell:
```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install -e . --no-deps
.venv\Scripts\python.exe scripts/start.py infra
.venv\Scripts\python.exe scripts/start.py prepare
.venv\Scripts\python.exe scripts/start.py api
```
`prepare` acquires current GTFS and the pilot OSM highway extract, validates/locks
pilot routes and flushes archived references. Its new source receipts cannot recreate
a time before acquisition. Local historic bootstrap files are an optional import via
`resilience bootstrap`, never a requirement for clean current-data setup.

Run collection in a second terminal: `python scripts/start.py collect` using the
virtual environment's Python. Outside weekday 06–12, `--force` records explicit local
preview captures. To make a snapshot: `resilience snapshot --as-of <aware ISO8601>`.
Health: `http://127.0.0.1:8000/v1/health`; OpenAPI: `/docs`.

Compose limits PostGIS and Redpanda to 1GB each and API to 2GB; ports bind localhost.
The official PostGIS image requires linux/amd64 emulation on the tested Apple Silicon
Mac; Redpanda remains native. Named volumes are project scoped. Use `docker compose
stop` to stop this project's services. Do not prune unrelated Docker objects.
Mac startup, live health, PostGIS storage and Redpanda deliveries were exercised.
Windows/Linux clean installs are CI matrix checks; no successful remote CI run is
claimed here. No Homebrew installation is required.

OTP is separate independent validation: official OTP 2.10.0 requires Java 25. Set up
Java and the official shaded JAR, then `python scripts/prepare_otp.py` and `python
scripts/convert_osm.py`. Run `java -Xmx2G -jar <OTP.jar> --build --save data/derived/otp`, then
`java -Xmx2G -jar <OTP.jar> --load --serve --port 8801 data/derived/otp`. See `INTEGRATION.md` for the actual routing blocker; graph startup
alone is not independent routing verification.
