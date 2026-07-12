"""project_workstations entity + seat.workstation_id

Revision ID: b8a2f4c91d77
Revises: d41db472ac7c
Create Date: 2026-05-08

Adds the logical workstation entity (软件/硬件/嵌入式 …) decoupled from
computer_node_id. Seats that previously carried only a computer_node_id get
migrated into a default workstation per node so existing data keeps working.
"""
from __future__ import annotations

import re
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8a2f4c91d77"
down_revision: Union[str, None] = "d41db472ac7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slug(value: str | None, *, prefix: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not text:
        text = f"{prefix}-{secrets.token_hex(3)}"
    return text


def upgrade() -> None:
    op.create_table(
        "project_workstations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("config_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lead_seat_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("review_policy", sa.String(length=32), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "config_id", name="uq_project_workstations_project_config_id"),
    )

    with op.batch_alter_table("project_thread_workstations") as batch:
        batch.add_column(sa.Column("workstation_id", sa.String(length=64), nullable=True))
        batch.create_index("ix_project_thread_workstations_workstation_id", ["workstation_id"])

    bind = op.get_bind()
    seats = bind.execute(
        sa.text(
            "SELECT id, project_id, computer_node_id FROM project_thread_workstations "
            "WHERE computer_node_id IS NOT NULL AND TRIM(computer_node_id) <> ''"
        )
    ).fetchall()

    seen: dict[tuple[str, str], str] = {}
    for seat_id, project_id, node_id in seats:
        key = (str(project_id), str(node_id))
        ws_id = seen.get(key)
        if not ws_id:
            ws_id = f"ws-{_slug(node_id, prefix='ws')}-{secrets.token_hex(2)}"
            label = bind.execute(
                sa.text(
                    "SELECT label FROM project_computer_nodes "
                    "WHERE project_id = :pid AND config_id = :nid LIMIT 1"
                ),
                {"pid": project_id, "nid": node_id},
            ).scalar()
            display_name = f"{label or node_id} 工位"
            bind.execute(
                sa.text(
                    "INSERT INTO project_workstations (id, project_id, config_id, name, description, sort_order) "
                    "VALUES (:id, :pid, :cid, :name, :desc, 0)"
                ),
                {
                    "id": ws_id,
                    "pid": project_id,
                    "cid": ws_id,
                    "name": display_name,
                    "desc": "由 computer_node 自动迁移；可改名为软件/硬件/嵌入式工位等",
                },
            )
            seen[key] = ws_id
        bind.execute(
            sa.text(
                "UPDATE project_thread_workstations SET workstation_id = :wid WHERE id = :sid"
            ),
            {"wid": ws_id, "sid": seat_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("project_thread_workstations") as batch:
        batch.drop_index("ix_project_thread_workstations_workstation_id")
        batch.drop_column("workstation_id")
    op.drop_table("project_workstations")
