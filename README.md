# RMS BMC

The repository is organized as a backend service, shared documentation, and a frontend app:

- `backend/` — FastAPI service, database migrations, and tests.
- `docs/` — project documentation.
- `frontend/` — Next.js application.

## Run the backend

See [backend/README.md](backend/README.md) for PostgreSQL setup, environment variables, migrations, tests and Docker. Quick start:

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env            # set DB_PASSWORD and JWT_SECRET_KEY
python -m alembic upgrade head
python -m scripts.seed --demo --admin-password "<10+ characters>"
python -m uvicorn app.main:app --reload --port 8000
```

Or the whole backend stack with Docker from this folder: `docker compose up -d --build` (copy `.env.example` to `.env` first).

Docs: [implementation plan](docs/IMPLEMENTATION_PLAN.md), [frontend integration](docs/FRONTEND_INTEGRATION.md), [requirements traceability](docs/TRACEABILITY.md).

## Run the frontend

```bash
cd frontend
npm ci
npm run dev
```
