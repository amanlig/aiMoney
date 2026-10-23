# FastAPI and Docker

React calls FastAPI on the same origin. FastAPI serves the React build at `/` and
`/covered-call-optimizer`; all holdings, saved captures, settings, scenarios and
recommendations use `/api/` routes. OpenAPI documentation is at `/docs`, the schema
at `/openapi.json`, and the health endpoint at `/api/health`.

## Local Python

From the `aiMoney` repository root:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
python frontend/build.py
python dashboard_server.py
```

The default bind is `127.0.0.1:8765`. Open
http://localhost:8765/covered-call-optimizer. `python dashboard_server.py --port
8766` selects another port. The separate closing worksheet server is unchanged.

## Docker Compose

The deployment now includes PostgreSQL. Set `POSTGRES_PASSWORD` in the untracked
`.env` file and follow [PostgreSQL migration](POSTGRESQL.md) before starting the
updated application against existing records. The `postgres_data` named volume
persists database records; `data/` retains holdings JSON and the legacy SQLite source.
Do not delete the database volume when replacing containers.


Docker Engine with Compose v2, or Docker Desktop with integration enabled for the
active WSL distribution, is required. Check `docker version` and `docker compose
version` from the Linux terminal.

Stop the local Python dashboard first; both use port 8765. Keep only one server
using the live data and Questrade refresh token at a time. In a new checkout,
prepare local directories (existing records are preserved):

```sh
mkdir -p data reports .secrets models/financials/cibc_fx/artifacts
chmod 700 .secrets
# If .env does not exist, record your local user for mounted-file permissions:
test -f .env || printf 'LOCAL_UID=%s\nLOCAL_GID=%s\n' "$(id -u)" "$(id -g)" > .env
```

Supply your existing reviewed holdings, credentials and optional FX model artifacts
in those directories. An empty checkout starts successfully, but needs position
records before analysis. Configure OpenAI locally with `python setup_openai.py`;
the resulting `.secrets/openai.json` is mounted into the container. Questrade setup
is described in `QUESTRADE.md`.

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail=50 api
curl http://localhost:8765/api/health
```

Open http://localhost:8765/covered-call-optimizer. To stop:

```sh
docker compose down
```

Data, reports and credentials use bind mounts, so records survive container
replacement. Credentials are writable because broker refresh tokens rotate. Model
artifacts mount read-only; the image contains code only. `.dockerignore` excludes
private material from the build context. The non-root runtime defaults to UID/GID
1000; for another Linux user run
`LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up --build -d` so mounted
file permissions match. Docker publishes the API on the host loopback only.

A single Uvicorn worker owns the periodic Yahoo feed and shared broker/OpenAI
locks. Do not add workers or replicas without replacing these in-process locks
with coordination across processes. Shutdown stops the feed through FastAPI's
lifespan hook. Mutation requests retain origin checks and body-size limits;
blocking broker, model, database and OpenAI services run in FastAPI's thread pool.
The UI never receives credentials. OCR uses Tesseract installed in the image.

## Verification

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_public_*.py'
python -m unittest discover -s tests -p test_fastapi.py
python -m unittest discover -s models/financials/covered_call_exit/tests
python -m unittest discover -s models/financials/cibc_fx/tests
node tests/test_public_calculations.js
```

API tests use temporary SQLite files and mocked market/assessment services. They
exercise validation, error contracts, origin and size limits, concurrency locks,
React assets and lifespan shutdown without contacting external services. Optional
Playwright browser tests now start Uvicorn with FastAPI and synthetic responses.

Implementation follows the [FastAPI container guidance](https://fastapi.tiangolo.com/deployment/docker/)
and [lifespan guidance](https://fastapi.tiangolo.com/advanced/events/).
