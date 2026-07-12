"""collaboration_messages.extra_data + receipts indexing

Revision ID: c6f1d2e8a39b
Revises: b8a2f4c91d77
Create Date: 2026-05-08

Adds an `extra_data` JSON column to collaboration_messages so receipts can
record `receipt_kind` (ack | progress | done | reject) and the
`parent_requirement_id` they refer back to. Also adds an index on
message_type for fast receipt filtering.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6f1d2e8a39b"
down_revision: Union[str, None] = "b8a2f4c91d77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("collaboration_messages") as batch:
        batch.add_column(sa.Column("extra_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("collaboration_messages") as batch:
        batch.drop_column("extra_data")
