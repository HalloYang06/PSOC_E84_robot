from __future__ import annotations

from sqlalchemy.orm import Session

from app.settings import get_settings
from app.seed import seed_if_empty


def ensure_seed_data(db: Session) -> None:
    if not get_settings().database_auto_seed:
        return
    seed_if_empty(db)
