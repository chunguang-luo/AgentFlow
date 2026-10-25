"""Establish the initial migration baseline.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-25
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No domain tables are created in phase 0.

    Alembic still writes its version table, allowing phase 1 migrations to have
    a stable predecessor and making upgrade/downgrade behavior reproducible.
    """


def downgrade() -> None:
    """Phase 0 has no application tables to remove."""
