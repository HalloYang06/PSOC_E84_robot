"""boss plan registry

Revision ID: f3b7a2c91e44
Revises: e2a9b7c43f10
Create Date: 2026-05-11

Adds formal Boss NPC planning records so project decomposition, dispatched
items, acknowledgements, and final receipts can be tracked beyond browser state.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b7a2c91e44"
down_revision: Union[str, None] = "e2a9b7c43f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "boss_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("boss_seat_id", sa.String(length=64), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_message_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("contract_path", sa.String(length=500), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("boss_plans") as batch:
        batch.create_index(batch.f("ix_boss_plans_boss_seat_id"), ["boss_seat_id"], unique=False)
        batch.create_index(batch.f("ix_boss_plans_project_id"), ["project_id"], unique=False)
        batch.create_index(batch.f("ix_boss_plans_source_message_id"), ["source_message_id"], unique=False)
        batch.create_index(batch.f("ix_boss_plans_status"), ["status"], unique=False)

    op.create_table(
        "boss_plan_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=160), nullable=False),
        sa.Column("target_seat_id", sa.String(length=64), nullable=True),
        sa.Column("target_name", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dispatch_message_id", sa.String(length=64), nullable=True),
        sa.Column("receipt_message_id", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("knowledge_paths", sa.JSON(), nullable=True),
        sa.Column("acceptance", sa.Text(), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["boss_plans.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "role", "target_seat_id", name="uq_boss_plan_items_plan_role_target"),
    )
    with op.batch_alter_table("boss_plan_items") as batch:
        batch.create_index(batch.f("ix_boss_plan_items_dispatch_message_id"), ["dispatch_message_id"], unique=False)
        batch.create_index(batch.f("ix_boss_plan_items_plan_id"), ["plan_id"], unique=False)
        batch.create_index(batch.f("ix_boss_plan_items_project_id"), ["project_id"], unique=False)
        batch.create_index(batch.f("ix_boss_plan_items_receipt_message_id"), ["receipt_message_id"], unique=False)
        batch.create_index(batch.f("ix_boss_plan_items_status"), ["status"], unique=False)
        batch.create_index(batch.f("ix_boss_plan_items_target_seat_id"), ["target_seat_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("boss_plan_items") as batch:
        batch.drop_index(batch.f("ix_boss_plan_items_target_seat_id"))
        batch.drop_index(batch.f("ix_boss_plan_items_status"))
        batch.drop_index(batch.f("ix_boss_plan_items_receipt_message_id"))
        batch.drop_index(batch.f("ix_boss_plan_items_project_id"))
        batch.drop_index(batch.f("ix_boss_plan_items_plan_id"))
        batch.drop_index(batch.f("ix_boss_plan_items_dispatch_message_id"))
    op.drop_table("boss_plan_items")

    with op.batch_alter_table("boss_plans") as batch:
        batch.drop_index(batch.f("ix_boss_plans_status"))
        batch.drop_index(batch.f("ix_boss_plans_source_message_id"))
        batch.drop_index(batch.f("ix_boss_plans_project_id"))
        batch.drop_index(batch.f("ix_boss_plans_boss_seat_id"))
    op.drop_table("boss_plans")
