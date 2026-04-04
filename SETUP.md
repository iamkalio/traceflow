# Local setup (developer)

This repo has three moving parts:

- **API** (FastAPI): OTLP ingest + REST endpoints
- **Worker** (RQ): runs eval jobs (groundedness + regression compare)
- **UI** (Next.js): dashboard

You can run everything with Docker Compose (recommended) or run services locally.

## Option A — Docker Compose (recommended)

1. Create an env file for Docker.

Copy `.env.docker.example` → `.env.docker` if you have it, or create `.env.docker` next to `docker-compose.yml` with at least:

```bash
OPENAI_API_KEY=sk-...
```

2. Start the stack.

```bash
docker compose up --build
```

3. Open the UI.

- **Dashboard**: `http://localhost:3000`
- **API**: `http://localhost:8000`

## Option B — Run locally (no Docker)

You still need **Postgres** + **Redis** running somewhere (local services or containers).

### 1) Start Postgres + Redis

If you want to use containers just for infra:

```bash
docker compose up -d postgres redis
```

### 2) Backend API

From repo root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/traceflow"
export REDIS_URL="redis://localhost:6379/0"

uvicorn main:app --reload --port 8000
```

### 3) Worker (eval jobs)

In a second terminal (same venv):

```bash
cd backend
source .venv/bin/activate

export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/traceflow"
export REDIS_URL="redis://localhost:6379/0"
export OPENAI_API_KEY="sk-..."

python3 -m modules.jobs.worker
```

### 4) UI (Next.js)

In a third terminal:

```bash
cd app
pnpm install
pnpm run dev
```

Open `http://localhost:3000`.

## Quick demo data (two traces)

Post two realistic demo traces (OTLP protobuf) to the ingest endpoint:

```bash
cd backend
pip install httpx opentelemetry-proto
BASE_URL=http://127.0.0.1:8000 python3 scripts/post_demo_traces.py
```

Then go to **Traces** in the UI and run the **groundedness** eval for either trace.

