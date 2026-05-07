from __future__ import annotations

import os
import tempfile
from pathlib import Path


os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-suite-secret"
os.environ["TOKEN_ENCRYPTION_KEY"] = "test-suite-token-key"
test_db_override = os.environ.get("TEST_DATABASE_PATH", "").strip()
default_test_db = Path(tempfile.gettempdir()) / f"ai_collab_test_suite_{os.getpid()}.db"
TEST_DATABASE_PATH = Path(test_db_override) if test_db_override else default_test_db
if TEST_DATABASE_PATH.exists():
    TEST_DATABASE_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["DATABASE_AUTO_CREATE"] = "true"
os.environ["DATABASE_AUTO_SEED"] = "true"
os.environ["ALLOW_BOOTSTRAP_AUTH"] = "false"

import app.db.models  # noqa: E402,F401
from sqlalchemy import select  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.modules.auth.schemas import RegisterRequest  # noqa: E402
from app.modules.auth.service import register_user  # noqa: E402
from app.seed import (  # noqa: E402
    ensure_sample_task_events,
    ensure_schema_extensions,
    normalize_sample_collaboration_config,
    normalize_sample_ids,
    normalize_sample_requirement_policy,
    normalize_sample_workflow_state,
    seed_if_empty,
)


Base.metadata.create_all(bind=engine)
ensure_schema_extensions()

with SessionLocal() as db:
    normalize_sample_ids(db)
    seed_if_empty(db)
    normalize_sample_ids(db)
    normalize_sample_workflow_state(db)
    normalize_sample_requirement_policy(db)
    normalize_sample_collaboration_config(db)
    ensure_sample_task_events(db)
    if db.scalar(select(User.id).where(User.email == "lead@example.com")) is None:
        register_user(
            db,
            RegisterRequest(
                email="lead@example.com",
                name="Test Lead",
                password="password",
            ),
        )
