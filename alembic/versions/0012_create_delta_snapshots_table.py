"""create delta_snapshots table

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delta_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_hash", sa.String(), nullable=False),
        sa.Column("underlying", sa.String(), nullable=False),
        sa.Column("spot", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("net_delta", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("short_call_symbol", sa.String(), nullable=True),
        sa.Column("short_call_delta", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("long_put_delta", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delta_snapshots_account_hash", "delta_snapshots", ["account_hash"])
    op.create_index("ix_delta_snapshots_underlying", "delta_snapshots", ["underlying"])
    op.create_index("ix_delta_snapshots_short_call_symbol", "delta_snapshots", ["short_call_symbol"])
    op.create_index("ix_delta_snapshots_recorded_at", "delta_snapshots", ["recorded_at"])
    op.create_index(
        "ix_delta_snapshots_acct_underlying_time",
        "delta_snapshots",
        ["account_hash", "underlying", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_delta_snapshots_acct_underlying_time", table_name="delta_snapshots")
    op.drop_index("ix_delta_snapshots_recorded_at", table_name="delta_snapshots")
    op.drop_index("ix_delta_snapshots_short_call_symbol", table_name="delta_snapshots")
    op.drop_index("ix_delta_snapshots_underlying", table_name="delta_snapshots")
    op.drop_index("ix_delta_snapshots_account_hash", table_name="delta_snapshots")
    op.drop_table("delta_snapshots")
