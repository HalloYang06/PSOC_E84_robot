# Infra (First Version)

This folder contains the first-version local infrastructure setup using Docker Compose.

## Services

- `postgres` (PostgreSQL 16)
- `redis` (Redis 7)
- `api` (FastAPI on port 8000)
- `web` (Next.js dev server on port 3000)

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)

## Run

From the repo root:

```powershell
docker compose -f infra/docker-compose.yml up --build
```

Open:

- Web: `http://localhost:3000`
- API health: `http://localhost:8000/api/health`

## Stop

```powershell
docker compose -f infra/docker-compose.yml down
```

## Notes

- The `api` service mounts `../apps/api/app` into the container for live reload.
- The `web` service mounts `../apps/web` and uses a named volume for `node_modules`.
- This is intentionally minimal for the first version.

