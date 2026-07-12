# Infra

This folder contains both a local development stack and a formal public deployment stack.

## Local Stack

### Services

- `postgres` (PostgreSQL 16)
- `redis` (Redis 7)
- `api` (FastAPI on port 8000 with reload)
- `web` (Next.js dev server on port 3000)

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)

### Run

From the repo root:

```powershell
docker compose -f platform/deploy/docker-compose.yml config
docker compose -f platform/deploy/docker-compose.yml up --build
```

Open:

- Web: `http://localhost:3000`
- API health: `http://localhost:8000/api/health`

### Stop

```powershell
docker compose -f platform/deploy/docker-compose.yml down
```

### Notes

- The `api` service mounts `../api/app` into the container for live reload.
- The `web` service mounts `../web` and uses a named volume for `node_modules`.
- This stack is intentionally minimal and stays local-first.

## Formal Public Deployment

Use these files for a real public server:

- `platform/deploy/docker-compose.public.yml`
- `platform/deploy/api.prod.Dockerfile`
- `platform/deploy/web.prod.Dockerfile`
- `platform/deploy/Caddyfile`
- `platform/deploy/.env.public.example`

### What this stack does

- exposes only `80` and `443` on the host
- terminates TLS in `Caddy`
- reverse proxies `/api/*` to the FastAPI container
- reverse proxies the web app to the Next.js production container
- keeps Postgres and Redis internal to the Docker network
- uses `INTERNAL_API_BASE_URL=http://api:8010` for server-side Next.js fetches
- turns on secure SuperTokens cookies in production

### First-time setup

1. Copy `platform/deploy/.env.public.example` to `platform/deploy/.env.public`
2. Replace every placeholder secret and SMTP value
3. Point `PUBLIC_APP_DOMAIN` at the server's real DNS name
4. Make sure ports `80` and `443` are open on the server firewall
5. Make sure Docker and Docker Compose are installed on the server

### Run the public stack

From the repo root:

```powershell
docker compose --env-file platform/deploy/.env.public -f platform/deploy/docker-compose.public.yml config
docker compose --env-file platform/deploy/.env.public -f platform/deploy/docker-compose.public.yml up -d --build
```

### Preflight check before deploy

Validate the resolved Compose configuration before the first deploy or after editing secrets:

```powershell
docker compose --env-file platform/deploy/.env.public -f platform/deploy/docker-compose.public.yml config
```

### Public health checks

- App: `https://your-domain.example/login`
- API: `https://your-domain.example/api/health`

### Important production notes

- Use a real domain. Automatic TLS is much less reliable on a raw IP.
- `ALLOW_BOOTSTRAP_AUTH`, `DATABASE_AUTO_CREATE`, and `DATABASE_AUTO_SEED` stay disabled in production.
- `PUBLIC_APP_DOMAIN` should match both the DNS record and the public browser origin.
- `INTERNAL_API_BASE_URL` should stay on the Docker network path (`http://api:8010`) so server-side web fetches do not loop back through the public edge.
