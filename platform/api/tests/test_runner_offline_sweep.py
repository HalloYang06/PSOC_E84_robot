"""Tests for ``mark_stale_runners_offline``.

The platform displays runner online/offline counts on the project shell and lab
service. Without a periodic sweep, ``Runner.status`` stays "online" forever
because only ``register`` and ``heartbeat`` write the column. This caused the
acceptance complaint "我刚接入 runner 时是在线的, 后面一堆操作不知道是不是掉了".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.models.runner import Runner
from app.db.session import SessionLocal
from app.main import app
from app.modules.runners.service import mark_stale_runners_offline


client = TestClient(app)


def _make_runner(runner_id: str, *, last_heartbeat_at, status: str = "online", created_at=None) -> None:
    with SessionLocal() as db:
        runner = db.get(Runner, runner_id)
        if runner is None:
            runner = Runner(id=runner_id, name=runner_id, capabilities=["python"], status=status)
            db.add(runner)
        runner.status = status
        runner.last_heartbeat_at = last_heartbeat_at
        if created_at is not None:
            runner.created_at = created_at
        db.commit()


def _runner_status(runner_id: str) -> str | None:
    with SessionLocal() as db:
        runner = db.get(Runner, runner_id)
        return runner.status if runner else None


def test_runner_with_fresh_heartbeat_stays_online() -> None:
    runner_id = "runner-fresh"
    _make_runner(runner_id, last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=30))

    with SessionLocal() as db:
        result = mark_stale_runners_offline(db)

    assert _runner_status(runner_id) == "online"
    flipped_ids = {row["runner_id"] for row in result["flipped"]}
    assert runner_id not in flipped_ids


def test_runner_with_stale_heartbeat_flips_offline() -> None:
    runner_id = "runner-stale"
    _make_runner(runner_id, last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=600))

    with SessionLocal() as db:
        result = mark_stale_runners_offline(db)

    assert _runner_status(runner_id) == "offline"
    flipped_ids = {row["runner_id"] for row in result["flipped"]}
    assert runner_id in flipped_ids
    flipped = next(row for row in result["flipped"] if row["runner_id"] == runner_id)
    assert flipped["before"] == "online"
    assert flipped["after"] == "offline"


def test_already_offline_runner_is_not_touched() -> None:
    runner_id = "runner-already-offline"
    _make_runner(runner_id, last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=600), status="offline")

    with SessionLocal() as db:
        result = mark_stale_runners_offline(db)

    assert _runner_status(runner_id) == "offline"
    flipped_ids = {row["runner_id"] for row in result["flipped"]}
    assert runner_id not in flipped_ids


def test_runner_never_heartbeated_but_just_created_is_left_alone() -> None:
    runner_id = "runner-just-registered"
    _make_runner(
        runner_id,
        last_heartbeat_at=None,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )

    with SessionLocal() as db:
        result = mark_stale_runners_offline(db)

    assert _runner_status(runner_id) == "online"
    flipped_ids = {row["runner_id"] for row in result["flipped"]}
    assert runner_id not in flipped_ids


def test_runner_never_heartbeated_and_old_is_marked_offline() -> None:
    runner_id = "runner-zombie"
    _make_runner(
        runner_id,
        last_heartbeat_at=None,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=600),
    )

    with SessionLocal() as db:
        result = mark_stale_runners_offline(db)

    assert _runner_status(runner_id) == "offline"
    flipped_ids = {row["runner_id"] for row in result["flipped"]}
    assert runner_id in flipped_ids
