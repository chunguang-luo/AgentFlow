"""Add provider logs and artifacts.

Revision ID: 0004_phase3
Revises: 0003_phase2
Create Date: 2026-10-25
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_phase3"
down_revision = "0003_phase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("step_run_id", sa.String(length=64), nullable=False),
        sa.Column("stream", sa.String(length=10), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stream IN ('stdout', 'stderr', 'system')", name="ck_agent_log_stream"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_agent_logs_run_id_runs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id"],
            ["step_runs.id"],
            name="fk_agent_logs_step_run_id_step_runs",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("step_run_id", "sequence", name="uq_agent_log_sequence"),
    )
    op.create_index(op.f("ix_agent_logs_run_id"), "agent_logs", ["run_id"])
    op.create_index(op.f("ix_agent_logs_step_run_id"), "agent_logs", ["step_run_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("step_run_id", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.String(length=512), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_artifacts_run_id_runs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id"],
            ["step_runs.id"],
            name="fk_artifacts_step_run_id_step_runs",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "relative_path", name="uq_run_artifact_path"),
    )
    op.create_index(op.f("ix_artifacts_run_id"), "artifacts", ["run_id"])
    op.create_index(op.f("ix_artifacts_step_run_id"), "artifacts", ["step_run_id"])


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("agent_logs")
