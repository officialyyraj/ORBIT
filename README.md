# ORBIT

ORBIT is a personalized learning roadmap system for introductory programming. It combines a seeded Knowledge Space Tree (KST), Bayesian Knowledge Tracing (BKT), a KST-informed lightweight recurrent DKT model, retention decay, weighted multi-objective A*, and Pareto-frontier roadmap alternatives.

The backend follows the `/api/v1` REST contract in `docs/05_API_CONTRACT.md`. Local development uses SQLite by default; `docker-compose.yml` runs the same application against PostgreSQL.

## Local development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m app.db.seed
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The seeded demo account is `demo@orbit.dev` with password `orbit-demo`.

## Docker

```bash
docker compose build --no-cache backend frontend
docker compose up
```

The backend image uses `python:3.12-slim-bookworm`, upgrades the packaging toolchain, installs the small native build toolchain for packages such as `cryptography`, `psycopg2`, `uvloop`, and `httptools`, and prefers binary wheels. Compose also waits for PostgreSQL health before seeding the backend. If Docker Desktop is still showing a cached failure, run `docker builder prune -af` once and repeat the two commands above. The original failure was reported only as pip exit code 2 without the package-level stderr; the pinned requirements install successfully in a clean Python 3.12 environment, so the revised image removes the likely native-wheel/build-context failure mode.

## Phase 6 capabilities

The backend now computes conditional-accuracy edge confidence from paired learner responses, persists the score, and exposes low-confidence edges through the admin review API. The seeded demo account is the local admin account by default; production deployments should set `ADMIN_EMAILS` to the desired administrator addresses.

The DKT implementation is a dependency-light recurrent model implemented with NumPy. Its embeddings are initialized from KST adjacency and two-hop adjacency features. It is selected only after `DKT_MIN_INTERACTIONS` responses, persists `source: "dkt"`, falls back to BKT if inference fails, and supports offline checkpoint training:

```bash
cd backend
PYTHONPATH=. python -m app.mastery.train_dkt --output dkt_checkpoint.json --epochs 8
```

The roadmap endpoint supports both `GET /api/v1/roadmap/me?mode=weighted` and `GET /api/v1/roadmap/me?mode=pareto`. Pareto mode exposes `Fastest`, `Best retention`, and `Balanced` alternatives, and the frontend includes a mode toggle with path-specific graph highlighting. The authenticated Edge review page provides the low-confidence list and a refinement action without automatically changing graph topology.

## Demo flow

Sign up or log in, complete the diagnostic quiz, open the dashboard and roadmap, switch between balanced and Pareto path modes, review the admin edge-confidence page, choose a recommended topic, and complete its topic quiz. Every response updates mastery and invalidates roadmap caches; the frontend invalidates its React Query caches and shows changed mastery and roadmap state without a manual browser refresh.

## Structured learning library

Use **Learning library** in the sidebar to browse the six initial tracks and study topic lessons before starting topic practice. The content is stored in the same `topics`/`topic_edges`/`questions` entities used by the existing BKT and roadmap flows. To repeat the deterministic, duplicate-safe seed/import after installing backend dependencies:

```bash
cd backend
PYTHONPATH=. python -m app.db.seed
```

The expanded curriculum and its verified counts are documented in `CONTENT_LIBRARY_STATUS.md`. The importer performs structural checks, is idempotent, and does not delete learner records.

## AI Lab

Authenticated learners can open **AI Lab** in the sidebar to inspect the persisted prerequisite graph (including per-track filtering and mastery status), step through the configured BKT calculation, trace the actual weighted-cost A* search, and run an integrated synthetic scenario. The BKT and A* diagnostic APIs are read-only. The integrated scenario can grade an approved question, but its synthetic answer/mastery state stays in memory and is not written to learner response or mastery tables. Automated isolation and algorithm regression tests are in `backend/app/tests/test_ai_lab_api.py` and `backend/app/tests/test_algorithms.py`; implementation and verification notes are in `AI_LAB_IMPLEMENTATION_CHECKLIST.md`.

See `docs/07_BUILD_ROADMAP.md` for the completed phase checklist and verification status.
