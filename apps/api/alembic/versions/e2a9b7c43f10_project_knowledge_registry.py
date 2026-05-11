"""project knowledge and skill registry

Revision ID: e2a9b7c43f10
Revises: c6f1d2e8a39b
Create Date: 2026-05-11

Formalizes GitHub repo-relative knowledge documents, project skills, and
NPC/seat skill assignments so the platform can move beyond page metadata.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a9b7c43f10"
down_revision: Union[str, None] = "c6f1d2e8a39b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_knowledge_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("repo_relative_path", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=700), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=True),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("exists_in_repo", sa.Boolean(), nullable=True),
        sa.Column("version_ref", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "repo_relative_path", name="uq_project_knowledge_documents_project_path"),
    )
    with op.batch_alter_table("project_knowledge_documents") as batch:
        batch.create_index(batch.f("ix_project_knowledge_documents_owner_id"), ["owner_id"], unique=False)
        batch.create_index(batch.f("ix_project_knowledge_documents_owner_type"), ["owner_type"], unique=False)
        batch.create_index(batch.f("ix_project_knowledge_documents_project_id"), ["project_id"], unique=False)
        batch.create_index(batch.f("ix_project_knowledge_documents_repo_relative_path"), ["repo_relative_path"], unique=False)
        batch.create_index(batch.f("ix_project_knowledge_documents_scope"), ["scope"], unique=False)

    op.create_table(
        "project_skills",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("skill_id", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("repo_relative_path", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=700), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recommended_for", sa.JSON(), nullable=True),
        sa.Column("exists_in_repo", sa.Boolean(), nullable=True),
        sa.Column("version_ref", sa.String(length=120), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "skill_id", name="uq_project_skills_project_skill"),
    )
    with op.batch_alter_table("project_skills") as batch:
        batch.create_index(batch.f("ix_project_skills_category"), ["category"], unique=False)
        batch.create_index(batch.f("ix_project_skills_project_id"), ["project_id"], unique=False)
        batch.create_index(batch.f("ix_project_skills_skill_id"), ["skill_id"], unique=False)
        batch.create_index(batch.f("ix_project_skills_source"), ["source"], unique=False)

    op.create_table(
        "seat_skill_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("seat_id", sa.String(length=64), nullable=False),
        sa.Column("skill_id", sa.String(length=120), nullable=False),
        sa.Column("assignment_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "seat_id", "skill_id", name="uq_seat_skill_assignments_project_seat_skill"),
    )
    with op.batch_alter_table("seat_skill_assignments") as batch:
        batch.create_index(batch.f("ix_seat_skill_assignments_project_id"), ["project_id"], unique=False)
        batch.create_index(batch.f("ix_seat_skill_assignments_seat_id"), ["seat_id"], unique=False)
        batch.create_index(batch.f("ix_seat_skill_assignments_skill_id"), ["skill_id"], unique=False)
        batch.create_index(batch.f("ix_seat_skill_assignments_assignment_type"), ["assignment_type"], unique=False)
        batch.create_index(batch.f("ix_seat_skill_assignments_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("seat_skill_assignments") as batch:
        batch.drop_index(batch.f("ix_seat_skill_assignments_status"))
        batch.drop_index(batch.f("ix_seat_skill_assignments_assignment_type"))
        batch.drop_index(batch.f("ix_seat_skill_assignments_skill_id"))
        batch.drop_index(batch.f("ix_seat_skill_assignments_seat_id"))
        batch.drop_index(batch.f("ix_seat_skill_assignments_project_id"))
    op.drop_table("seat_skill_assignments")

    with op.batch_alter_table("project_skills") as batch:
        batch.drop_index(batch.f("ix_project_skills_source"))
        batch.drop_index(batch.f("ix_project_skills_skill_id"))
        batch.drop_index(batch.f("ix_project_skills_project_id"))
        batch.drop_index(batch.f("ix_project_skills_category"))
    op.drop_table("project_skills")

    with op.batch_alter_table("project_knowledge_documents") as batch:
        batch.drop_index(batch.f("ix_project_knowledge_documents_scope"))
        batch.drop_index(batch.f("ix_project_knowledge_documents_repo_relative_path"))
        batch.drop_index(batch.f("ix_project_knowledge_documents_project_id"))
        batch.drop_index(batch.f("ix_project_knowledge_documents_owner_type"))
        batch.drop_index(batch.f("ix_project_knowledge_documents_owner_id"))
    op.drop_table("project_knowledge_documents")
