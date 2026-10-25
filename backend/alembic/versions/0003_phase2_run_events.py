"""Add run event stream for execution progress.

Revision ID: 0003_phase2
Revises: 0002_phase1
Create Date: 2026-10-25
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_phase2"
down_revision = "0002_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("step_run_id", sa.String(length=64), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_run_events_run_id_runs", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),
    )
    op.create_index(op.f("ix_run_events_run_id"), "run_events", ["run_id"])
    op.create_index(op.f("ix_run_events_event_type"), "run_events", ["event_type"])
    op.create_index("ix_run_events_run_sequence", "run_events", ["run_id", "sequence"])


def downgrade() -> None:
    op.drop_table("run_events")
