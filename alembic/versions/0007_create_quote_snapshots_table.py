"""create quote_snapshots table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quote_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("bid_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("ask_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("open_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("high_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("low_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("close_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("raw", JSONB(), nullable=False),
        sa.Column("quoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_snapshots_symbol", "quote_snapshots", ["symbol"])
    op.create_index("ix_quote_snapshots_quoted_at", "quote_snapshots", ["quoted_at"])
    op.create_index(
        "ix_quote_snapshots_symbol_quoted_at",
        "quote_snapshots",
        ["symbol", "quoted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_quote_snapshots_symbol_quoted_at", table_name="quote_snapshots")
    op.drop_index("ix_quote_snapshots_quoted_at", table_name="quote_snapshots")
    op.drop_index("ix_quote_snapshots_symbol", table_name="quote_snapshots")
    op.drop_table("quote_snapshots")
