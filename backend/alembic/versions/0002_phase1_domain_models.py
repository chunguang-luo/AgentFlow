"""Create phase 1 domain tables.

Revision ID: 0002_phase1
Revises: 0001_baseline
Create Date: 2026-10-25
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_phase1"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True, unique=True),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin', 'editor', 'operator', 'viewer')", name="ck_user_role"
        ),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "flows",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("draft_definition", sa.JSON(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_flow_status"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_flows_owner_id_users"),
    )
    op.create_index(op.f("ix_flows_name"), "flows", ["name"])
    op.create_index(op.f("ix_flows_status"), "flows", ["status"])
    op.create_index(op.f("ix_flows_owner_id"), "flows", ["owner_id"])

    op.create_table(
        "flow_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("flow_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["flow_id"], ["flows.id"], name="fk_flow_versions_flow_id_flows", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("flow_id", "version", name="uq_flow_version"),
    )
    op.create_index(op.f("ix_flow_versions_flow_id"), "flow_versions", ["flow_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("flow_id", sa.String(length=64), nullable=False),
        sa.Column("flow_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled', 'timeout')",
            name="ck_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["flow_id"], ["flows.id"], name="fk_runs_flow_id_flows", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("flow_id", "idempotency_key", name="uq_flow_idempotency"),
    )
    op.create_index(op.f("ix_runs_flow_id"), "runs", ["flow_id"])
    op.create_index(op.f("ix_runs_status"), "runs", ["status"])
    op.create_index(op.f("ix_runs_idempotency_key"), "runs", ["idempotency_key"])
    op.create_index("ix_runs_flow_created", "runs", ["flow_id", "created_at"])

    op.create_table(
        "step_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=100), nullable=False),
        sa.Column("step_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'running', 'succeeded', 'failed', "
            "'skipped', 'cancelled', 'timeout')",
            name="ck_step_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_step_runs_run_id_runs", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("run_id", "step_id", "attempt", name="uq_step_run_attempt"),
    )
    op.create_index(op.f("ix_step_runs_run_id"), "step_runs", ["run_id"])
    op.create_index(op.f("ix_step_runs_status"), "step_runs", ["status"])
    op.create_index(op.f("ix_step_runs_step_id"), "step_runs", ["step_id"])
    op.create_index("ix_step_runs_run_step", "step_runs", ["run_id", "step_id"])


def downgrade() -> None:
    op.drop_table("step_runs")
    op.drop_table("runs")
    op.drop_table("flow_versions")
    op.drop_table("flows")
    op.drop_table("users")
