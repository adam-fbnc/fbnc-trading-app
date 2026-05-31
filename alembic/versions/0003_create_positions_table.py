"""create positions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_hash", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("cusip", sa.String(), nullable=True),
        sa.Column("asset_type", sa.String(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("current_value", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("raw", JSONB(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_hash"], ["accounts.account_hash"], ondelete="CASCADE"),
    )
    op.create_index("ix_positions_account_hash", "positions", ["account_hash"])
    op.create_index("ix_positions_symbol", "positions", ["symbol"])
    op.create_index("ix_positions_cusip", "positions", ["cusip"])


def downgrade() -> None:
    op.drop_index("ix_positions_cusip", table_name="positions")
    op.drop_index("ix_positions_symbol", table_name="positions")
    op.drop_index("ix_positions_account_hash", table_name="positions")
    op.drop_table("positions")
