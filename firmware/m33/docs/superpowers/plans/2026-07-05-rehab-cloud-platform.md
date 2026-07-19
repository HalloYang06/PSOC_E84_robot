# Rehab Cloud Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deployable backend MVP for the real Stitch rehab app with login, profile, device binding, sessions, and rehab-agent chat.

**Architecture:** Add an isolated FastAPI service under `cloud/rehab-platform/`. Business logic is testable without HTTP, while routers expose the JSON contract already consumed by `github.com/wenjunyong666/ai-` branch `app/rehab-arm-mobile-stitch`, especially `apps/web/public/rehab-arm-mobile/mobile-bridge.js`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic Settings, pytest, Docker Compose, optional OpenAI-compatible agent provider.

---

## File Structure

- `cloud/rehab-platform/pyproject.toml`: Python package and test dependencies.
- `cloud/rehab-platform/README.md`: local run, Docker, API summary, Stitch handoff.
- `cloud/rehab-platform/.env.example`: safe environment template.
- `cloud/rehab-platform/docker-compose.yml`: API, PostgreSQL, Redis.
- `cloud/rehab-platform/Dockerfile`: production API image.
- `cloud/rehab-platform/app/main.py`: FastAPI application factory.
- `cloud/rehab-platform/app/core/config.py`: settings.
- `cloud/rehab-platform/app/db.py`: SQLAlchemy engine/session helpers.
- `cloud/rehab-platform/app/models.py`: ORM models.
- `cloud/rehab-platform/app/schemas.py`: request/response schemas.
- `cloud/rehab-platform/app/security.py`: passwords, verification-code hashing, JWT helpers.
- `cloud/rehab-platform/app/repositories.py`: persistence helpers.
- `cloud/rehab-platform/app/services/auth.py`: phone-code and token flow.
- `cloud/rehab-platform/app/services/devices.py`: device claim flow.
- `cloud/rehab-platform/app/services/sessions.py`: training-session flow.
- `cloud/rehab-platform/app/services/agent.py`: safe rehab-agent context and provider boundary.
- `cloud/rehab-platform/app/api/deps.py`: API dependencies.
- `cloud/rehab-platform/app/api/routes/*.py`: HTTP routes, including compatibility routes under `/api/rehab-arm/app/v1`.
- `cloud/rehab-platform/tests/*.py`: pytest coverage.
- `docs/stitch/rehab-app-v1-prompt.md`: Stitch prompt and API contract for the real app branch.

## Tasks

### Task 1: Service Skeleton and Auth Business Tests

- [ ] Create failing tests for existing app login via `POST /api/auth/session` and token-protected `GET /api/rehab-arm/app/v1/me`.
- [ ] Implement settings, DB session, user/code models, security helpers, auth service, and app-compatible auth routes.
- [ ] Run `python -m pytest tests/test_auth.py -v`.

### Task 2: Patient Profile

- [ ] Create failing tests for reading default profile and updating patient details.
- [ ] Implement profile schema, model fields, service behavior, and routes.
- [ ] Run `python -m pytest tests/test_profile.py -v`.

### Task 3: Device Registry and Binding

- [ ] Create failing tests for `POST /api/rehab-arm/app/v1/devices/bind`, listing devices through `/me`, and SPP inbound evidence upload.
- [ ] Implement device and claim models, seed helper, device service, and app-compatible routes.
- [ ] Run `python -m pytest tests/test_devices.py -v`.

### Task 4: Training Sessions

- [ ] Create failing tests for uploading a session summary and listing recent sessions.
- [ ] Implement session model, schemas, service, and routes.
- [ ] Run `python -m pytest tests/test_sessions.py -v`.

### Task 5: Rehab Agent

- [ ] Create failing tests that AI training draft generation uses profile/session context and blocks unsafe motion commands.
- [ ] Implement deterministic local draft generation plus optional OpenAI-compatible provider behind configuration.
- [ ] Run `python -m pytest tests/test_agent.py -v`.

### Task 6: Packaging, Docker, and Stitch Handoff

- [ ] Add Dockerfile, compose file, env example, README, and Stitch prompt.
- [ ] Run the full backend test suite.
- [ ] If dependencies allow, start the API locally and QA `/health` plus OpenAPI in the browser plugin.

### Task 7: Cloud Deploy and Install Package Gate

- [ ] Deploy the completed milestone to the cloud server.
- [ ] Run cloud smoke tests against the public API base used by the app.
- [ ] Build or refresh the installable app package.
- [ ] Install/smoke-test the package or at least verify the packaged artifact opens the deployed API.
- [ ] Record the deployed URL, package path, build version, and smoke-test result before calling the milestone complete.

## Self-Review

- The plan covers auth, profile, device binding, sessions, agent, deployment, and frontend handoff.
- There are no placeholder sections.
- The MVP avoids direct motor authority and keeps the M33/NanoPi safety boundary intact.
- Major tasks include a deployment and install-package gate.
