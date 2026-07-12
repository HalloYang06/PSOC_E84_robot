"""Realtime event bus.

WebSocket endpoint that streams project-scoped events (runner heartbeat,
task events, collaboration messages, NPC handoff progress) to subscribed
UI clients in near real-time.

Design:
- In-memory broker keyed by project_id (one process, single instance for now).
- Endpoint: ws /api/realtime/projects/{project_id}/events
- Token via query string `?token=...` (HTTP Bearer not portable to WS).
- Other modules import `publish(project_id, event)` to broadcast.

This is the smallest useful surface to remove polling from the UI; later
this can swap to Redis pub/sub for multi-process deployments without
touching the public protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.common.access import verify_access_token
from app.db.models.project_member import ProjectMember
from app.db.session import SessionLocal
from sqlalchemy import select


router = APIRouter(prefix="/api/realtime", tags=["realtime"])
logger = logging.getLogger(__name__)


_subscribers: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


def _serialize(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.setdefault("ts", datetime.now(timezone.utc).isoformat())
    return json.dumps(payload, ensure_ascii=False, default=str)


async def publish(project_id: str, event: dict[str, Any]) -> int:
    """Broadcast `event` to every WS subscriber listening on `project_id`.

    Returns the number of clients the event was delivered to. Failed sockets
    are removed silently. Safe to call from anywhere on the asyncio loop.
    """
    if not project_id:
        return 0
    payload = _serialize(event)
    delivered = 0
    dead: list[WebSocket] = []
    async with _lock:
        targets = list(_subscribers.get(project_id, ()))
    for ws in targets:
        try:
            await ws.send_text(payload)
            delivered += 1
        except Exception:
            dead.append(ws)
    if dead:
        async with _lock:
            for ws in dead:
                _subscribers.get(project_id, set()).discard(ws)
    return delivered


def publish_sync(project_id: str, event: dict[str, Any]) -> None:
    """Schedule a publish from a sync context (e.g. SQLAlchemy after_commit)."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if loop.is_running():
        asyncio.ensure_future(publish(project_id, event))
    else:
        try:
            loop.run_until_complete(publish(project_id, event))
        except Exception:
            pass


def _user_can_read_project(user_id: str | None, project_id: str) -> bool:
    if not user_id:
        return False
    with SessionLocal() as db:
        membership = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.status == "active",
            )
        )
        return membership is not None


@router.websocket("/projects/{project_id}/events")
async def project_event_stream(
    websocket: WebSocket,
    project_id: str,
    token: str = Query("", description="Access token issued by /api/auth/session"),
):
    """Subscribe to project events. Sends `{type: 'hello', ...}` on connect.

    Heartbeat: server sends `{type: 'ping'}` every 30s; clients should send
    `{type: 'pong'}` back, but the server tolerates silence.
    """
    payload = verify_access_token(token) if token else None
    user_id = payload.get("sub") if payload else None
    if not user_id or not _user_can_read_project(user_id, project_id):
        await websocket.close(code=4401, reason="unauthorized")
        return

    await websocket.accept()
    async with _lock:
        _subscribers[project_id].add(websocket)
    subscribers_now = len(_subscribers[project_id])

    await websocket.send_text(_serialize({
        "type": "hello",
        "project_id": project_id,
        "subscribers": subscribers_now,
        "user_id": user_id,
    }))

    async def _heartbeat():
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_text(_serialize({"type": "ping"}))
        except Exception:
            return

    hb_task = asyncio.create_task(_heartbeat())
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if data.get("type") == "echo":
                await websocket.send_text(_serialize({"type": "echo_ack", "received": data}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("realtime ws error: %s", exc)
    finally:
        hb_task.cancel()
        async with _lock:
            _subscribers.get(project_id, set()).discard(websocket)
