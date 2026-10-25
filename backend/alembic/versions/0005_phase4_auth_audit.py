"""Add authentication sessions and audit logs.

Revision ID: 0005_phase4
Revises: 0004_phase3
Create Date: 2026-10-25
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_phase4"
down_revision = "0004_phase3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users"),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ("
            "'auth.login_succeeded', 'auth.login_failed', 'auth.logout', "
            "'flow.created', 'flow.updated', 'flow.published', 'flow.imported', "
            "'flow.exported', 'run.created', 'run.cancelled', 'run.retried', "
            "'provider.health_checked')",
            name="ck_audit_log_action",
        ),
    )
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"])
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(op.f("ix_audit_logs_target_type"), "audit_logs", ["target_type"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("sessions")
