from __future__ import annotations

import asyncio
import logging
import os
import socket

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.errors import AppError
from app.common.request_id import new_request_id, set_request_id
from app.common.response import err, ok
import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.settings import get_settings
from app.supertokens_runtime import setup_supertokens
from app.seed import (
    ensure_sample_task_events,
    ensure_schema_extensions,
    normalize_sample_ids,
    normalize_sample_collaboration_config,
    normalize_sample_requirement_policy,
    normalize_sample_workflow_state,
    seed_if_empty,
)
from app.modules.agents.router import router as agents_router
from app.modules.approvals.router import router as approvals_router
from app.modules.auth.router import router as auth_router
from app.modules.audit.router import router as audit_router
from app.modules.boss_plans.router import router as boss_plans_router
from app.modules.collaboration.router import router as collaboration_router
from app.modules.context.router import router as context_router
from app.modules.development.router import router as development_router
from app.modules.git.router import router as git_router
from app.modules.handoffs.router import router as handoffs_router
from app.modules.lab.router import router as lab_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.messages.router import router as messages_router
from app.modules.projects.router import router as projects_router
from app.modules.requirements.router import router as requirements_router
from app.modules.runners.router import router as runners_router
from app.modules.runners.service import mark_stale_runners_offline
from app.modules.seats.router import router as seats_router
from app.modules.tasks.router import router as tasks_router
from app.modules.usage.router import router as usage_router
from app.modules.workstations.router import router as workstations_router
from app.modules.claude_bridge.router import router as claude_bridge_router
from app.modules.qualification.router import router as qualification_router
from app.modules.realtime.router import router as realtime_router
from app.modules.receipts.router import router as receipts_router

_log = logging.getLogger(__name__)

# Run the sweeper this often. Heartbeat staleness threshold is
# RUNNER_WATCH_FRESH_SECONDS (180s) — we re-check every 60s so a freshly-stopped
# runner shows offline within ~3.5 min worst case.
RUNNER_OFFLINE_SWEEP_INTERVAL_SECONDS = 60


app = FastAPI(title="AI Collab Platform API", version="0.1.0")
settings = get_settings()
SERVICE_HEALTH_PORTS = (3000, 8010, 8011)

if settings.cors_allowed_origins_list and not settings.supertokens_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

setup_supertokens(app, settings)


def _port_has_listener(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.08)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _local_service_probe() -> list[dict[str, object]]:
    return [
        {
            "host": "127.0.0.1",
            "port": port,
            "listening": _port_has_listener(port),
        }
        for port in SERVICE_HEALTH_PORTS
    ]


def _health_payload(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "pid": os.getpid(),
        "host": request.url.hostname,
        "port": request.url.port,
        "base_url": str(request.base_url).rstrip("/"),
        "local_services": _local_service_probe(),
    }


def _startup_settings():
    return get_settings()


def _ensure_runtime_configuration() -> None:
    settings = _startup_settings()
    if settings.is_production:
        if not settings.secret_key.strip():
            raise RuntimeError("SECRET_KEY must be configured in production")
        if settings.allow_bootstrap_auth:
            raise RuntimeError("ALLOW_BOOTSTRAP_AUTH must stay disabled in production")
        if settings.database_auto_create:
            raise RuntimeError("DATABASE_AUTO_CREATE must stay disabled in production")
        if settings.database_auto_seed:
            raise RuntimeError("DATABASE_AUTO_SEED must stay disabled in production")


@app.on_event("startup")
def on_startup() -> None:
    settings = _startup_settings()
    _ensure_runtime_configuration()

    if settings.database_auto_create:
        Base.metadata.create_all(bind=engine)

    # Keep local SQLite deployments self-healing when models add columns/indexes.
    # This must also run for existing databases, not only on fresh create.
    ensure_schema_extensions()

    if settings.database_auto_seed and settings.app_env.strip().lower() == "test":
        with SessionLocal() as db:
            normalize_sample_ids(db)
            seed_if_empty(db)
            normalize_sample_ids(db)
            normalize_sample_workflow_state(db)
            normalize_sample_requirement_policy(db)
            normalize_sample_collaboration_config(db)
            ensure_sample_task_events(db)


async def _runner_offline_sweep_loop() -> None:
    """Background task: every minute, mark runners with stale heartbeats offline.

    Skipped during pytest (app_env="test") so unit tests stay deterministic.
    Errors are caught and logged but never crash the loop — a single failed
    sweep should not take the API down.
    """
    interval = RUNNER_OFFLINE_SWEEP_INTERVAL_SECONDS
    while True:
        try:
            await asyncio.sleep(interval)
            await asyncio.to_thread(_run_runner_offline_sweep_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("runner offline sweep iteration failed")


def _run_runner_offline_sweep_once() -> dict[str, object]:
    with SessionLocal() as db:
        result = mark_stale_runners_offline(db)
    flipped = int(result.get("flipped_count") or 0)
    if flipped:
        _log.info("runner offline sweep: flipped %s runners offline", flipped)
    return result


@app.on_event("startup")
async def _start_runner_offline_sweeper() -> None:
    settings = _startup_settings()
    if settings.app_env.strip().lower() == "test":
        return
    app.state.runner_offline_sweep_task = asyncio.create_task(_runner_offline_sweep_loop())


@app.on_event("shutdown")
async def _stop_runner_offline_sweeper() -> None:
    task = getattr(app.state, "runner_offline_sweep_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or new_request_id()
    set_request_id(rid)
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=err(exc.code, exc.message, details=exc.details))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=err("VALIDATION_ERROR", "请求参数校验失败", details={"errors": exc.errors()}),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    code = "UNAUTHORIZED" if exc.status_code == 401 else "PERMISSION_DENIED" if exc.status_code == 403 else "HTTP_ERROR"
    return JSONResponse(status_code=exc.status_code, content=err(code, str(exc.detail)))


@app.get("/api/health")
def health(request: Request) -> dict[str, object]:
    return ok(_health_payload(request))


@app.get("/health")
def health_short(request: Request) -> dict[str, object]:
    return ok(_health_payload(request))


@app.get("/static/seat-mcp-server.py")
def serve_seat_mcp_server() -> Response:
    """Expose seat-mcp-server.py for one-shot setup script consumption.

    Used by scripts/setup-seat-mcp.{ps1,sh} so worker PCs can pull a fresh copy
    without needing access to the source repo. Read-only; no auth required —
    the file is published source code, not a secret."""
    from pathlib import Path
    from fastapi import HTTPException

    candidates = [
        Path(__file__).resolve().parents[3] / "scripts" / "seat-mcp-server" / "server.py",
        Path.cwd() / "scripts" / "seat-mcp-server" / "server.py",
    ]
    for path in candidates:
        if path.is_file():
            return Response(content=path.read_text(encoding="utf-8"), media_type="text/x-python; charset=utf-8")
    raise HTTPException(status_code=404, detail="seat-mcp-server.py not found on this host")


app.include_router(projects_router)
app.include_router(auth_router)
app.include_router(requirements_router)
app.include_router(agents_router)
app.include_router(runners_router)
app.include_router(tasks_router)
app.include_router(context_router)
app.include_router(development_router)
app.include_router(handoffs_router)
app.include_router(lab_router)
app.include_router(knowledge_router)
app.include_router(messages_router)
app.include_router(approvals_router)
app.include_router(audit_router)
app.include_router(boss_plans_router)
app.include_router(collaboration_router)
app.include_router(git_router)
app.include_router(usage_router)
app.include_router(claude_bridge_router)
app.include_router(qualification_router)
app.include_router(realtime_router)
app.include_router(workstations_router)
app.include_router(seats_router)
app.include_router(receipts_router)
