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
The Verification workflow checks Python on macOS, Linux and Windows and installs, tests and builds the frontend. Candidate-specific outcomes are retained with each release. No Homebrew installation is required.

OTP is separate independent validation: official OTP 2.10.0 requires Java 25. Set up
Java and the official shaded JAR, then `python scripts/prepare_otp.py` and `python
scripts/convert_osm.py`. Run `java -Xmx2G -jar <OTP.jar> --build --save data/derived/otp`, then
`java -Xmx2G -jar <OTP.jar> --load --serve --port 8801 data/derived/otp`. See `REFERENCE_VALIDATION.md` for the exact morning comparison scope and retained access differences. Graph startup alone is not routing verification.

Persistent collector: using the environment Python, `python scripts/install_collector.py`
prepares a user service locally; add `--install` to install/start it, or `--remove` to
remove it. The actual Mac LaunchAgent was installed and checked by the coordinator;
Windows Task Scheduler XML/install commands are generated portably but await a real
Windows check. Docker services now declare `restart:unless-stopped`; apply with
`docker compose up -d postgres redpanda`. Docker Desktop itself must start after login.

For analysis, use `python scripts/run_experiments.py --snapshot <id> --prepare-only`
to freeze source targets, then choose a predefined scenario/budget. The fixed pair list
is committed; its absent future stop ids remain unavailable, preserving 100 requests.
`--sensitivity --budgets 2 --scenario stop_closure` compares 0/300/600-second additional
bus directional running time with identical candidate IDs. Running calculations need
a stable API process: avoid automatic code reload during jobs. Restarted jobs are
explicitly failed and must be resubmitted under new ids.

For verified offline artifacts and exact recomputation, follow `REPRODUCTION.md`.
`RELEASE.md` describes candidate preparation and final evidence checks. The committed
release configuration is a pending template. Populate candidate evidence only in an
ignored runtime file and set `RESILIENCE_RELEASE_EVIDENCE` to its path after freezing
a clean candidate revision; pending gates must never be changed without reviewed facts.
