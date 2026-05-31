"""create account_snapshots table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_hash", sa.String(), nullable=False),
        sa.Column("cash_balance", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("equity_value", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("buying_power", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("long_market_value", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("short_market_value", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("day_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("raw", JSONB(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_hash"], ["accounts.account_hash"], ondelete="CASCADE"),
    )
    op.create_index("ix_account_snapshots_account_hash", "account_snapshots", ["account_hash"])
    op.create_index("ix_account_snapshots_snapshot_at", "account_snapshots", ["snapshot_at"])


def downgrade() -> None:
    op.drop_index("ix_account_snapshots_snapshot_at", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_account_hash", table_name="account_snapshots")
    op.drop_table("account_snapshots")
